# validators.py
from datetime import datetime
import re
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

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
        raise ValidationError(f"{value} is not a valid date format. Use YYYY-MM-DD.")

def LinkValidator(link):
    """
    Validate a link URL.
    """
    url_validator = URLValidator()
    try:
        url_validator(link)
    except ValidationError:
        raise ValidationError(f"{link} is not a valid URL.")

def NameValidator(value):
    """
    Validate name value (example: only letters and spaces).
    """
    if not re.match(r'^[A-Za-z\s]+$', value):
        raise ValidationError(f"{value} is not a valid name. Only letters and spaces are allowed.")