"""
WSGI config for DataSpace project.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")

# Initialize OpenTelemetry before application
from api.telemetry import setup_telemetry

setup_telemetry()  # Initialize telemetry for production application

application = get_wsgi_application()
