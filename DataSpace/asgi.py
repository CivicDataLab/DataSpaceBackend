"""
ASGI config for DataSpace project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")

# Initialize OpenTelemetry before application
from api.telemetry import setup_telemetry

setup_telemetry()  # Initialize telemetry for ASGI application

application = get_asgi_application()
