# validators.py
from datetime import datetime
import re

def DateValidator(value):
    """
    function that validates date value

    Args:
        date_str (str): The date string to validate.

    Returns:
        bool: True if the date is valid, False otherwise.
    """

    try:
        datetime.strptime(value, '%Y-%m-%d')  # Adjust the date format as needed after discussing
        return True
    except ValueError:
        return False

def LinkValidator(link):
    """
    Validate a link URL.

    Args:
        link (str): The link URL to validate.

    Returns:
        bool: True if the link is valid, False otherwise.
    """
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https:// or ftp://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return bool(re.match(url_pattern, link))

def NameValidator(value):
    return value