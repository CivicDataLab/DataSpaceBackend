from typing import Any, Callable, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject

from authorization.consent import UserConsent

# mypy: disable-error-code=no-any-return
# mypy: disable-error-code=attr-defined


class ActivityConsentMiddleware:
    """
    Middleware to check if a user has given consent for activity tracking.
    This middleware adds a 'has_activity_consent' attribute to the request object.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Add the has_activity_consent attribute to the request
        # This is lazy to avoid unnecessary database queries
        request.has_activity_consent = SimpleLazyObject(
            lambda: self._get_user_consent(request)
        )
        return self.get_response(request)

    def _get_user_consent(self, request: HttpRequest) -> bool:
        """
        Check if the user has given consent for activity tracking based on settings.
        If REQUIRE_CONSENT is False, consent is assumed for authenticated users.
        """
        # Get consent settings
        require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
            "REQUIRE_CONSENT", True
        )
        default_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
            "DEFAULT_CONSENT", False
        )
        track_anonymous = getattr(settings, "ACTIVITY_CONSENT", {}).get(
            "TRACK_ANONYMOUS", False
        )

        # If consent is not required, return True for authenticated users
        # and track_anonymous setting for anonymous users
        if not require_consent:
            if not request.user or not request.user.is_authenticated:
                return bool(track_anonymous)
            return True

        # If consent is required, check if the user has given consent
        if not request.user or not request.user.is_authenticated:
            return False

        consent, created = UserConsent.objects.get_or_create(
            user=request.user, defaults={"activity_tracking_enabled": default_consent}
        )
        return consent.activity_tracking_enabled
