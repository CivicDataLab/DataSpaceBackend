from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from api.models import Organization, DataSpace


class ContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_token = request.headers.get('authorization', None)
        organization_slug = request.headers.get('organization', None)
        dataspace_slug = request.headers.get('dataspace', None)

        # Validate and load the organization and dataspace objects
        try:
            if organization_slug is None:
                organization = None
            else:
                organization = get_object_or_404(Organization, slug=organization_slug)
            if dataspace_slug is None:
                dataspace = None
            else:
                dataspace = get_object_or_404(DataSpace, slug=dataspace_slug)
        except Organization.DoesNotExist:
            return JsonResponse({"error": "Invalid organization slug"}, status=400)
        except DataSpace.DoesNotExist:
            return JsonResponse({"error": "Invalid group slug"}, status=400)

        # TODO: resolve auth_token to user object before passing
        request.context = {
            'auth_token': auth_token,
            'organization': organization,
            'dataspace': dataspace
        }

        response = self.get_response(request)

        return response
