from typing import Any, Dict, Generator, Optional

import pandas as pd
import structlog
from django.db import connections, transaction
from django.db.utils import ProgrammingError

from api.models.Resource import Resource, ResourceDataTable
from api.models.ResourceSchema import ResourceSchema
from api.types.type_preview_data import PreviewData
from api.utils.file_utils import load_tabular_data

logger = structlog.get_logger("dataspace.data_indexing")

# Use a separate database for data tables
DATA_DB = "data_db"  # This should match the connection name in settings.py


def get_sql_type(pandas_dtype: str) -> str:
    """Convert pandas dtype to SQL type."""
    if "int" in pandas_dtype:
        return "BIGINT"
    elif "float" in pandas_dtype:
        return "DOUBLE PRECISION"
    elif "datetime" in pandas_dtype:
        return "TIMESTAMP"
    elif "bool" in pandas_dtype:
        return "BOOLEAN"
    else:
        return "TEXT"


def create_table_for_resource(
    resource: Resource, df: pd.DataFrame
) -> Optional[ResourceDataTable]:
    """Create a database table for the resource data and index it."""
    try:
        # Create ResourceDataTable entry first to get the table name
        data_table = ResourceDataTable.objects.create(resource=resource)
        table_name = data_table.table_name

        # Get column types
        column_types = {col: get_sql_type(str(df[col].dtype)) for col in df.columns}

        # Create table in the data database
        with connections[DATA_DB].cursor() as cursor:
            # Drop table if exists
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')

            # Create table with proper column types
            columns = [f'"{col}" {dtype}' for col, dtype in column_types.items()]
            create_table_sql = f'CREATE TABLE "{table_name}" ({", ".join(columns)})'
            cursor.execute(create_table_sql)

            # Create temporary table for COPY
            temp_table = f"temp_{table_name}"
            cursor.execute(f'CREATE TEMP TABLE "{temp_table}" (LIKE "{table_name}")')

            # Copy data to temp table
            quoted_columns = [f'"{col}"' for col in df.columns]
            # Use StringIO to create a file-like object for the CSV data
            from io import StringIO

            csv_data = StringIO()
            df.to_csv(csv_data, index=False, header=False)
            csv_data.seek(0)

            copy_sql = (
                f'COPY "{temp_table}" ({",".join(quoted_columns)}) FROM STDIN WITH CSV'
            )
            cursor.copy_expert(copy_sql, csv_data)

            # Insert from temp to main table with validation
            cursor.execute(f'INSERT INTO "{table_name}" SELECT * FROM "{temp_table}"')
            cursor.execute(f'DROP TABLE "{temp_table}"')

        return data_table

    except Exception as e:
        logger.error(f"Error creating table for resource {resource.id}: {str(e)}")
        if "data_table" in locals():
            data_table.delete()
        return None


def index_resource_data(resource: Resource) -> Optional[ResourceDataTable]:
    """Index a resource's CSV data into a database table.

    This function handles the indexing process gracefully, catching and logging
    specific errors at each stage of the process without crashing.

    Args:
        resource: The Resource object to index

    Returns:
        Optional[ResourceDataTable]: The created data table or None if indexing failed
    """
    resource_id = getattr(resource, "id", "unknown")

    try:
        # Check if resource is a supported tabular file
        try:
            file_details = resource.resourcefiledetails
            if not file_details:
                logger.info(
                    f"Resource {resource_id} has no file details, skipping indexing"
                )
                return None
        except Exception as e:
            logger.error(
                f"Failed to access file details for resource {resource_id}: {str(e)}"
            )
            return None

        # Check file format
        try:
            format = file_details.format.lower()
            supported_formats = [
                "csv",
                "xls",
                "xlsx",
                "ods",
                "parquet",
                "feather",
                "json",
                "tsv",
            ]
            if format not in supported_formats:
                logger.info(
                    f"Resource {resource_id} has unsupported format: {format}, skipping indexing"
                )
                return None
        except Exception as e:
            logger.error(
                f"Failed to determine format for resource {resource_id}: {str(e)}"
            )
            return None

        # Load tabular data with timeout protection
        try:
            import signal
            from contextlib import contextmanager

            @contextmanager
            def timeout(seconds: int) -> Generator[None, None, None]:
                def handler(signum: int, frame: Any) -> None:
                    raise TimeoutError(
                        f"Loading data timed out after {seconds} seconds"
                    )

                # Set the timeout handler
                original_handler = signal.getsignal(signal.SIGALRM)
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(seconds)
                try:
                    yield
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, original_handler)

            # Apply timeout only on Unix-based systems where signal.SIGALRM is available
            try:
                with timeout(60):  # 60 second timeout for loading data
                    df = load_tabular_data(file_details.file.path, format)
            except TimeoutError as te:
                logger.error(
                    f"Timeout while loading data for resource {resource_id}: {str(te)}"
                )
                return None
            except Exception:
                # Fallback without timeout if signal.SIGALRM is not available (e.g., on Windows)
                df = load_tabular_data(file_details.file.path, format)

            if df is None:
                logger.error(
                    f"Failed to load data for resource {resource_id}: Data loading returned None"
                )
                return None
            if df.empty:
                logger.info(f"Resource {resource_id} has empty data, skipping indexing")
                return None

            # Check for problematic column names and sanitize them
            try:
                # Replace problematic characters in column names
                # Create a new list of sanitized column names
                sanitized_columns = [
                    str(col).replace('"', "").replace("\n", " ").replace("\t", " ")
                    for col in df.columns
                ]
                # Assign to df.columns using pandas Index constructor
                df.columns = pd.Index(sanitized_columns)

                # Check for duplicate column names after sanitization
                if len(df.columns) != len(set(df.columns)):
                    # Handle duplicate columns by adding suffixes
                    from collections import Counter

                    col_counter = Counter(df.columns)
                    for col, count in col_counter.items():
                        if count > 1:
                            # Find all occurrences of this column name
                            indices = [i for i, x in enumerate(df.columns) if x == col]
                            # Rename all but the first occurrence
                            for i, idx in enumerate(indices[1:], 1):
                                df.columns.values[idx] = f"{col}_{i}"
                    logger.warning(
                        f"Renamed duplicate columns in resource {resource_id}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to sanitize column names for resource {resource_id}: {str(e)}"
                )
                return None

        except Exception as e:
            import traceback

            logger.error(
                f"Failed to load data for resource {resource_id}: {str(e)}\n{traceback.format_exc()}"
            )
            return None

        # Create and index table within transaction
        try:
            with transaction.atomic():
                # Delete existing table if any
                try:
                    existing_table = ResourceDataTable.objects.get(resource=resource)
                    try:
                        with connections[DATA_DB].cursor() as cursor:
                            cursor.execute(
                                f'DROP TABLE IF EXISTS "{existing_table.table_name}"'
                            )
                    except Exception as drop_error:
                        logger.error(
                            f"Failed to drop existing table for resource {resource_id}: {str(drop_error)}"
                        )
                        # Continue anyway as we'll try to recreate the table

                    existing_table.delete()
                except ResourceDataTable.DoesNotExist:
                    pass
                except Exception as e:
                    logger.error(
                        f"Error handling existing table for resource {resource_id}: {str(e)}"
                    )
                    # Continue with table creation

                # Create new table
                data_table = create_table_for_resource(resource, df)
                if not data_table:
                    logger.error(f"Failed to create table for resource {resource_id}")
                    return None

                # Update resource schema
                try:
                    # Store existing schema descriptions to preserve them during re-indexing
                    existing_schemas: Dict[str, Dict[str, Optional[str]]] = {}
                    for schema in ResourceSchema.objects.filter(
                        resource=resource
                    ):  # type: ResourceSchema
                        existing_schemas[schema.field_name] = {
                            "description": schema.description,
                            "format": schema.format,
                        }

                    # Clear existing schema for this resource
                    ResourceSchema.objects.filter(resource=resource).delete()

                    # Then create new schema entries for each column, preserving descriptions where possible
                    schema_success_count = 0
                    schema_error_count = 0

                    for col in df.columns:
                        try:
                            # Determine format - always use the detected format from the data
                            sql_type = get_sql_type(str(df[col].dtype))

                            # Map SQL types to FieldTypes enum values
                            if sql_type == "BIGINT":
                                format_value = "INTEGER"
                            elif sql_type == "DOUBLE PRECISION":
                                format_value = "NUMBER"
                            elif sql_type == "TIMESTAMP":
                                format_value = "DATE"
                            elif sql_type == "BOOLEAN":
                                format_value = "BOOLEAN"
                            else:  # TEXT or any other type
                                format_value = "STRING"

                            # For description, preserve existing if available, otherwise auto-generate
                            description = f"Description of column {col}"
                            if col in existing_schemas:
                                existing_description = existing_schemas[col][
                                    "description"
                                ]
                                # Check for None and non-auto-generated descriptions
                                if existing_description is not None:
                                    description = existing_description
                                    logger.debug(
                                        f"Preserved custom description for column {col}"
                                    )

                            # Create the schema entry
                            ResourceSchema.objects.create(
                                resource=resource,
                                field_name=col,
                                format=format_value,
                                description=description,
                            )
                            schema_success_count += 1
                        except Exception as schema_error:
                            schema_error_count += 1
                            logger.error(
                                f"Error creating schema for column {col} in resource {resource_id}: {str(schema_error)}"
                            )
                            # Continue with other columns even if one fails

                    logger.info(
                        f"Resource {resource_id} schema creation: {schema_success_count} columns succeeded, {schema_error_count} failed"
                    )
                except Exception as schema_error:
                    logger.error(
                        f"Failed to update schema for resource {resource_id}: {str(schema_error)}"
                    )
                    # Continue and return the data_table even if schema update fails

                return data_table
        except Exception as tx_error:
            import traceback

            logger.error(
                f"Transaction error for resource {resource_id}: {str(tx_error)}\n{traceback.format_exc()}"
            )
            return None

    except Exception as e:
        import traceback

        logger.error(
            f"Unexpected error indexing resource {resource_id}: {str(e)}\n{traceback.format_exc()}"
        )
        return None


def query_resource_data(resource: Resource, query: str) -> Optional[pd.DataFrame]:
    """Query data from a resource's indexed table."""
    try:
        data_table = ResourceDataTable.objects.get(resource=resource)
        with connections[DATA_DB].cursor() as cursor:
            cursor.execute(query.replace("{{table}}", f'"{data_table.table_name}"'))
            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=columns)
    except (ResourceDataTable.DoesNotExist, ProgrammingError) as e:
        import traceback

        logger.error(
            f"Error querying resource {resource.id} with query {query} : {str(e)} , traceback: {traceback.format_exc()}"
        )
        return None


def get_row_count(resource: Resource) -> int:
    """Get the number of rows in the table."""
    try:
        # First check if the data table exists without making a database connection
        try:
            data_table = ResourceDataTable.objects.get(resource=resource)
        except ResourceDataTable.DoesNotExist:
            return 0

        # Set a timeout for the database query
        import time

        from django.db import connection

        # Use a timeout to prevent long-running queries
        with connections[DATA_DB].cursor() as cursor:
            # Set statement timeout to 2 seconds
            cursor.execute("SET statement_timeout = 2000")
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{data_table.table_name}"')
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except Exception as query_error:
                logger.error(
                    f"Query timeout or error for resource {resource.id}: {str(query_error)}"
                )
                return 0
    except Exception as e:
        import traceback

        error_tb = traceback.format_exc()
        logger.error(
            f"Error getting row count for resource {resource.id}:\n{str(e)}\n{error_tb}"
        )
        return 0


def get_preview_data(resource: Resource) -> Optional[PreviewData]:
    try:
        if not resource.preview_enabled:
            return None

        preview_details = getattr(resource, "preview_details", None)
        if not preview_details:
            return None

        # First check if the data table exists without making a database connection
        try:
            data_table = ResourceDataTable.objects.get(resource=resource)
        except ResourceDataTable.DoesNotExist:
            logger.info(f"No data table exists for resource {resource.id}")
            return None

        is_all_entries = getattr(preview_details, "is_all_entries", False)
        start_entry = getattr(preview_details, "start_entry", 0)
        end_entry = getattr(
            preview_details, "end_entry", 10
        )  # Default to showing 10 rows if not specified

        # Use a timeout to prevent long-running queries
        with connections[DATA_DB].cursor() as cursor:
            # Set statement timeout to 3 seconds
            cursor.execute("SET statement_timeout = 3000")

            try:
                if is_all_entries:
                    # For safety, always limit the number of rows returned even for 'all entries'
                    cursor.execute(
                        f'SELECT * FROM "{data_table.table_name}" LIMIT 1000'
                    )
                else:
                    # Ensure we have valid integer values for the calculation
                    start = int(start_entry) if start_entry is not None else 0
                    end = int(end_entry) if end_entry is not None else 10
                    limit = min(end - start + 1, 1000)  # Cap at 1000 rows for safety
                    cursor.execute(
                        f'SELECT * FROM "{data_table.table_name}" LIMIT {limit} OFFSET {start}'
                    )

                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()
                # Convert tuples to lists
                rows = [list(row) for row in data]
                return PreviewData(columns=columns, rows=rows)
            except Exception as query_error:
                logger.error(
                    f"Query timeout or error for resource {resource.id}: {str(query_error)}"
                )
                return None
    except Exception as e:
        import traceback

        logger.error(
            f"Error getting preview data for resource {resource.id}: {str(e)}, traceback: {traceback.format_exc()}"
        )
        return None
