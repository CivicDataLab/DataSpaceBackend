from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from api.models import Organization, DataSpace


class ContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_token = request.headers.get('authorization', None)
        organization_id = request.headers.get('organization', None)
        dataspace_id = request.headers.get('dataspace', None)

        # Validate and load the organization and dataspace objects
        try:
            if organization_id is None:
                organization = None
            else:
                organization = get_object_or_404(Organization, id=organization_id)
            if dataspace_id is None:
                dataspace = None
            else:
                dataspace = get_object_or_404(DataSpace, id=dataspace_id)
        except Organization.DoesNotExist:
            return JsonResponse({"error": "Invalid organization ID"}, status=400)
        except DataSpace.DoesNotExist:
            return JsonResponse({"error": "Invalid group ID"}, status=400)

        # TODO: resolve auth_token to user object before passing
        request.context = {
            'auth_token': auth_token,
            'organization': organization,
            'dataspace': dataspace
        }

        response = self.get_response(request)

        return response
