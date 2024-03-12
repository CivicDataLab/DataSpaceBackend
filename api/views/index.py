from django.http import HttpResponse
from dataexbackend import settings


def index(request):
    return HttpResponse(settings.WELCOME_TEXT)
