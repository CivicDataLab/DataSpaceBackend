from typing import List, Optional

from django.db import models

from api.utils.enums import GeoTypes


class Geography(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=75, unique=True)
    code = models.CharField(
        max_length=100, null=True, blank=True, unique=False, default=""
    )
    type = models.CharField(max_length=20, choices=GeoTypes.choices)
    parent_id = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, default=None
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    def get_all_descendant_names(self) -> List[str]:
        """
        Get all descendant geography names including self.
        This is used for hierarchical filtering - when a parent geography is selected,
        all child geographies should also be included in the filter.

        Returns:
            List of geography names including self and all descendants
        """
        descendants = [self.name]
        children = Geography.objects.filter(parent_id=self.id)

        for child in children:
            descendants.extend(child.get_all_descendant_names())  # type: ignore[attr-defined]

        return descendants

    @classmethod
    def get_geography_names_with_descendants(
        cls, geography_names: List[str]
    ) -> List[str]:
        """
        Given a list of geography names, return all names including their descendants.
        This is a helper method for filtering that expands parent geographies to include children.

        Args:
            geography_names: List of geography names to expand

        Returns:
            List of geography names including all descendants
        """
        all_names = set()

        for name in geography_names:
            try:
                geography = cls.objects.get(name=name)
                all_names.update(geography.get_all_descendant_names())
            except cls.DoesNotExist:
                # If geography doesn't exist, just add the name as-is
                all_names.add(name)

        return list(all_names)

    class Meta:
        db_table = "geography"
        verbose_name_plural = "geographies"
        ordering = ["name"]
