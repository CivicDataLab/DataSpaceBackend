import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Union

import magic
import pandas as pd


def check_ext(file_object: Any) -> Optional[str]:
    ext_type = mimetypes.guess_type(file_object.name)[0]
    return ext_type


def check_mime_type(file_object: Any) -> Any:
    # with open(file_object.file) as mime_file:
    mime_type = magic.from_buffer(file_object.read(), mime=True)
    # file_object.file.close()
    return mime_type


def file_validation(
    file_object: Any, ext_object: Any, mapping: Dict[str, str]
) -> Optional[Any]:
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


@lru_cache()
def load_csv(filepath: str) -> pd.DataFrame:
    """Load CSV file into a pandas DataFrame.

    Args:
        filepath: Path to the CSV file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_csv(filepath)
