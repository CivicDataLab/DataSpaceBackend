"""Model for relationship between usecases and organizations."""

from django.db import models

from api.utils.enums import OrganizationRelationshipType


class UseCaseOrganizationRelationship(models.Model):
    """Intermediate model for UseCase-Organization relationship.
    This model stores the type of relationship between a usecase and an organization.
    """

    usecase = models.ForeignKey("api.UseCase", on_delete=models.CASCADE)
    organization = models.ForeignKey("api.Organization", on_delete=models.CASCADE)
    relationship_type = models.CharField(
        max_length=50,
        choices=OrganizationRelationshipType.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "usecase_organization_relationship"
        unique_together = ("usecase", "organization", "relationship_type")
        verbose_name = "UseCase Organization Relationship"
        verbose_name_plural = "UseCase Organization Relationships"

    def __str__(self) -> str:
        return f"{self.usecase.title} - {self.organization.name} ({self.relationship_type})"
