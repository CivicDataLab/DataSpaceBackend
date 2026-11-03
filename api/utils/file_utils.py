import mimetypes
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

import magic
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


def check_ext(file_object: Any) -> Optional[str]:
    ext_type = mimetypes.guess_type(file_object.name)[0]
    return ext_type


@contextmanager
def local_copy(fieldfile: Any) -> Iterator[str]:
    """Yield the path of a temporary local copy of a stored file.

    Media lives in S3, which has no local path, but pandas, libmagic and the
    YAML/XML parsers need one. The copy keeps the file's extension (some
    readers sniff it) and is removed on exit, even if the caller raises.
    """
    suffix = os.path.splitext(fieldfile.name)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        fieldfile.open("rb")
        try:
            for chunk in fieldfile.chunks():
                tmp.write(chunk)
        finally:
            fieldfile.close()
        tmp.flush()
        yield tmp.name


def check_mime_type(file_object: Any) -> Any:
    # Prefer from_file: libmagic 5.46 misidentifies zip buffers as
    # application/octet-stream via from_buffer, while from_file works.
    if hasattr(file_object, "storage"):
        with local_copy(file_object) as file_path:
            return magic.from_file(file_path, mime=True)
    return magic.from_buffer(file_object.read(), mime=True)


def file_validation(file_object: Any, ext_object: Any, mapping: Dict[str, str]) -> Optional[Any]:
    ext_type = check_ext(ext_object)
    print("ext--", ext_type)
    mime_type = check_mime_type(file_object)
    print("mime--", mime_type)
    if ext_type and mime_type:
        if mapping.get(ext_type.lower()) == mapping.get(mime_type.lower()):
            return mime_type
        else:
            return None
    else:
        return None


def get_file_extension(filename: str) -> Optional[str]:
    """Get the file extension from a filename."""
    _, ext = os.path.splitext(filename)
    return ext[1:] if ext else None


def get_mime_type(filename: str) -> Optional[str]:
    """Get the MIME type for a file."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type


def get_file_size(file_path: str) -> int:
    """Get the size of a file in bytes."""
    return os.path.getsize(file_path)


def ensure_directory_exists(directory_path: str) -> None:
    """Ensure a directory exists, create it if it doesn't."""
    os.makedirs(directory_path, exist_ok=True)


def get_relative_path(base_path: Union[str, Path], full_path: Union[str, Path]) -> str:
    """Get relative path from base path."""
    return os.path.relpath(full_path, base_path)


def join_paths(*paths: Union[str, Path]) -> str:
    """Join path components."""
    return os.path.join(*paths)


def normalize_path(path: Union[str, Path]) -> str:
    """Normalize path separators."""
    return os.path.normpath(str(path))


def load_csv(filepath: str) -> pd.DataFrame:
    """Load CSV file into a pandas DataFrame.

    Args:
        filepath: Path to the CSV file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_csv(filepath)


def load_excel(filepath: str) -> pd.DataFrame:
    """Load Excel file into a pandas DataFrame.

    Args:
        filepath: Path to the Excel file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_excel(filepath)


def load_ods(filepath: str) -> pd.DataFrame:
    """Load ODS file into a pandas DataFrame.

    Args:
        filepath: Path to the ODS file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_excel(filepath, engine="odf")


def load_parquet(filepath: str) -> pd.DataFrame:
    """Load Parquet file into a pandas DataFrame.

    Args:
        filepath: Path to the Parquet file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_parquet(filepath)


def load_feather(filepath: str) -> pd.DataFrame:
    """Load Feather file into a pandas DataFrame.

    Args:
        filepath: Path to the Feather file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_feather(filepath)


def load_json(filepath: str) -> pd.DataFrame:
    """Load JSON file into a pandas DataFrame.

    Args:
        filepath: Path to the JSON file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_json(filepath)


def load_tsv(filepath: str) -> pd.DataFrame:
    """Load TSV file into a pandas DataFrame.

    Args:
        filepath: Path to the TSV file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_csv(filepath, sep="\t")


def load_tabular_data(filepath: str, format: str) -> Optional[pd.DataFrame]:
    """Load tabular data from various file formats into a pandas DataFrame.

    Args:
        filepath: Path to the file
        format: File format (csv, xls, xlsx, ods, parquet, feather, json, tsv)

    Returns:
        Optional[pd.DataFrame]: Loaded DataFrame or None if format not supported
    """
    format = format.lower()
    format_handlers = {
        "csv": load_csv,
        "xls": load_excel,
        "xlsx": load_excel,
        "ods": load_ods,
        "parquet": load_parquet,
        "feather": load_feather,
        "json": load_json,
        "tsv": load_tsv,
    }

    handler = format_handlers.get(format)
    if handler:
        try:
            return handler(filepath)
        except Exception as e:
            logger.error(f"Error loading {format} file: {str(e)}")
            return None
    return None
