from django.db import models


class UseCaseDashboard(models.Model):
    """
    Model to store dashboard information for usecases.
    Each usecase can have multiple dashboards with names and links.
    """

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, blank=False, null=False)
    link = models.URLField(blank=False, null=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    usecase = models.ForeignKey(
        "api.UseCase", on_delete=models.CASCADE, related_name="dashboards"
    )

    class Meta:
        db_table = "usecase_dashboard"
        ordering = ["created"]

    def __str__(self):
        return f"{self.name} - {self.usecase.title if self.usecase else 'No Usecase'}"
