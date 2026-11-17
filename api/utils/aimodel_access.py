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
