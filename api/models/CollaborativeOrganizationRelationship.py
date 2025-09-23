"""Model for relationship between collaborative and organizations."""

from django.db import models

from api.utils.enums import OrganizationRelationshipType


class CollaborativeOrganizationRelationship(models.Model):
    """Intermediate model for Collaborative-Organization relationship.
    This model stores the type of relationship between a collaborative and an organization.
    """

    collaborative = models.ForeignKey("api.Collaborative", on_delete=models.CASCADE)
    organization = models.ForeignKey("api.Organization", on_delete=models.CASCADE)
    relationship_type = models.CharField(
        max_length=50,
        choices=OrganizationRelationshipType.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "collaborative_organization_relationship"
        unique_together = ("collaborative", "organization", "relationship_type")
        verbose_name = "Collaborative Organization Relationship"
        verbose_name_plural = "Collaborative Organization Relationships"

    def __str__(self) -> str:
        return f"{self.collaborative.title} - {self.organization.name} ({self.relationship_type})"
