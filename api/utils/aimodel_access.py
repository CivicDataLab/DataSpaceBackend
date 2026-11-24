"""Who may see an AI model.

Everyone sees a published model: public, active and ACTIVE/APPROVED, the same
rule the search index uses. Drafts (REGISTERED and the other statuses) are seen
only by their owner, members of their organisation whose role can view, and
superusers. `isPublic` alone is not enough: the dashboard sets it when details
are saved, long before the model is published (#293).
"""

from typing import Any

from django.db.models import Q, QuerySet

from api.models.AIModel import AIModel
from api.utils.enums import AIModelStatus
from authorization.models import OrganizationMembership

PUBLISHED_AI_MODEL_STATUSES = [AIModelStatus.ACTIVE, AIModelStatus.APPROVED]


def published_ai_models_q() -> Q:
    """The published rule as a filter for querysets."""
    return Q(is_public=True, is_active=True, status__in=PUBLISHED_AI_MODEL_STATUSES)


def published_ai_models() -> QuerySet:
    return AIModel.objects.filter(published_ai_models_q())


def is_published_ai_model(model: AIModel) -> bool:
    return bool(model.is_public and model.is_active and model.status in PUBLISHED_AI_MODEL_STATUSES)


def can_view_ai_model(user: Any, model: AIModel) -> bool:
    """Published models for everyone; drafts for owner, viewing org members, superusers."""
    if is_published_ai_model(model):
        return True
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or model.user_id == user.id:
        return True
    if model.organization_id:
        membership = (
            OrganizationMembership.objects.filter(user=user, organization_id=model.organization_id)
            .select_related("role")
            .first()
        )
        return bool(membership and membership.role and membership.role.can_view)
    return False


def can_change_ai_model(user: Any, model: AIModel) -> bool:
    """Owner, members of its organisation whose role can change, superusers.

    The same rule the AI model update mutations check inline.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or model.user_id == user.id:
        return True
    if model.organization_id:
        return OrganizationMembership.objects.filter(
            user=user, organization_id=model.organization_id, role__can_change=True
        ).exists()
    return False


def can_read_model_secrets(info: Any, model: AIModel) -> bool:
    """Whether this request may read the model's saved credentials (API keys,
    auth tokens, auth headers). Only people who can change the model need them.

    Cached on the request: one listing resolves several secret fields per
    provider, and they all ask about the same few models.
    """
    request = info.context
    cache = getattr(request, "_ai_model_secret_access", None)
    if cache is None:
        cache = {}
        try:
            setattr(request, "_ai_model_secret_access", cache)
        except AttributeError:
            pass  # context that takes no attributes: just don't cache
    if model.id not in cache:
        cache[model.id] = can_change_ai_model(getattr(request, "user", None), model)
    return bool(cache[model.id])
