"""Service functions for managing external contributors."""

import structlog
from django.db import transaction

from api.models import ExternalContributor
from authorization.models import User

logger = structlog.getLogger(__name__)


def is_email_already_user(email: str) -> bool:
    """Check if an email belongs to a registered user."""
    if not email:
        return False
    return User.objects.filter(email__iexact=email.strip()).exists()


def merge_external_contributor_into_user(user: User) -> bool:
    """Merge an external ExternalContributor into a registered User, rewiring all credits.

    Idempotent: safe to call on every login. Returns True if a merge happened,
    False if no matching ExternalContributor was found or email is blank.
    """
    if not user.email:
        return False

    email_clean = user.email.strip()

    try:
        external_contributor = ExternalContributor.objects.filter(email__iexact=email_clean).first()
    except Exception:
        return False

    if not external_contributor:
        return False

    contributor_id = external_contributor.id
    try:
        with transaction.atomic():
            # Rewire all M2M credits to the user. .add() is idempotent.
            user.contributed_usecases.add(*external_contributor.usecases.all())
            user.contributed_collaboratives.add(*external_contributor.collaboratives.all())
            user.contributed_publications.add(*external_contributor.publications.all())

            # Delete the now-redundant ExternalContributor row.
            image = external_contributor.image
            external_contributor.delete()

        # Remove the image file only once the delete has committed.
        if image:
            image.delete(save=False)
        return True
    except Exception as e:
        # Never break login on merge failure; log and continue.
        logger.error(
            f"Error merging external contributor {contributor_id} into user {user.id}: {e}"
        )
        return False
