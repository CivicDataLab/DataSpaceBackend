# mypy: disable-error-code=no-untyped-def
from django.db import models
from django.utils import timezone


class UserConsent(models.Model):
    """
    Model to track user consent for activity tracking.
    """

    user = models.OneToOneField(
        "authorization.User", on_delete=models.CASCADE, related_name="activity_consent"
    )
    activity_tracking_enabled = models.BooleanField(default=False)
    consent_given_at = models.DateTimeField(null=True, blank=True)
    consent_updated_at = models.DateTimeField(auto_now=True)
    consent_ip_address = models.GenericIPAddressField(null=True, blank=True)
    consent_user_agent = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Update consent_given_at when consent is enabled
        if self.activity_tracking_enabled and not self.consent_given_at:
            self.consent_given_at = timezone.now()
        # If consent is revoked, keep the consent_given_at for audit purposes
        super().save(*args, **kwargs)

    class Meta:
        db_table = "user_consent"
        verbose_name = "User Consent"
        verbose_name_plural = "User Consents"
