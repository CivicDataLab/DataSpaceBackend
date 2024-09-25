import os
from django.core.asgi import get_asgi_application
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Set up Django application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dataexbackend.settings')
application = get_asgi_application()

# Uvicorn configuration
uvicorn_config = {
    'host': os.getenv('UVICORN_HOST', '127.0.0.1'),
    'port': int(os.getenv('UVICORN_PORT', '8000')),
    'workers': int(os.getenv('UVICORN_WORKERS', '1')),
    'reload': True
}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("dataexbackend.asgi:application", **uvicorn_config)