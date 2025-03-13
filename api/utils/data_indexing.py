from typing import Any, Dict, List, Optional

import pandas as pd
import structlog
from django.conf import settings
from django.db import connections, transaction
from django.db.utils import ProgrammingError

from api.models.Resource import Resource, ResourceDataTable
from api.models.ResourceSchema import ResourceSchema
from api.utils.file_utils import load_csv

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
    """Index a resource's CSV data into a database table."""
    try:
        # Check if resource is a CSV file
        file_details = resource.resourcefiledetails
        if not file_details or not file_details.format.lower() == "csv":
            return None

        # Load CSV data
        df = load_csv(file_details.file.path)
        if df is None or df.empty:
            return None

        # Create and index table
        with transaction.atomic():
            # Delete existing table if any
            try:
                existing_table = ResourceDataTable.objects.get(resource=resource)
                with connections[DATA_DB].cursor() as cursor:
                    cursor.execute(
                        f'DROP TABLE IF EXISTS "{existing_table.table_name}"'
                    )
                existing_table.delete()
            except ResourceDataTable.DoesNotExist:
                pass

            # Create new table
            data_table = create_table_for_resource(resource, df)
            if data_table:
                # Update resource schema
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
                        description = f"Auto-generated from CSV column {col}"
                        if col in existing_schemas:
                            existing_description = existing_schemas[col]["description"]
                            # Check for None and non-auto-generated descriptions
                            if (
                                existing_description is not None
                                and not existing_description.startswith(
                                    "Auto-generated"
                                )
                            ):
                                description = existing_description
                                logger.info(
                                    f"Preserved custom description for column {col}"
                                )

                        # Create the schema entry
                        ResourceSchema.objects.create(
                            resource=resource,
                            field_name=col,
                            format=format_value,
                            description=description,
                        )
                    except Exception as schema_error:
                        logger.error(
                            f"Error creating schema for column {col}: {str(schema_error)}"
                        )
                        # Continue with other columns even if one fails

            return data_table

    except Exception as e:
        logger.error(f"Error indexing resource {resource.id}: {str(e)}")
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
        logger.error(f"Error querying resource {resource.id}: {str(e)}")
        return None
