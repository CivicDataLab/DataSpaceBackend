FORMAT_MAPPING = {
    "text/csv": "CSV",
    "csv": "CSV",
    "application/csv": "CSV",
    "application/json": "JSON",
    "json": "JSON",
    # "application/msword": "DOC",
    # "application/doc": "DOC",
    # "application/ms-doc": "DOC",
    "application/pdf": "PDF",
    # "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.ms-excel": "XLS",
    "application/xml": "XML",
    "xml": "XML",
    "text/xml": "XML",
    "application/geo+json": "JSON",
    "application/gml+xml": "XML",
    "application/xhtml+xml": "XML",
    # TODO: handle csv identified as text/plain
    "text/plain": "CSV",
    "application/zip": "ZIP",
}

IMAGE_FORMAT_MAPPING = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/svg+xml": "SVG",
}
