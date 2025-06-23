# mypy: disable-error-code=no-untyped-def
from rest_framework import serializers

from authorization.consent import UserConsent


class UserConsentSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserConsent model.
    """

    class Meta:
        model = UserConsent
        fields = ["activity_tracking_enabled", "consent_given_at", "consent_updated_at"]
        read_only_fields = ["consent_given_at", "consent_updated_at"]

    def update(self, instance, validated_data):
        # Get the request from the context
        request = self.context.get("request")

        # If we're enabling tracking, record the IP and user agent
        if validated_data.get("activity_tracking_enabled", False):
            if request:
                # Get the client IP address
                x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
                if x_forwarded_for:
                    # Take the first IP and strip whitespace, limit length for security
                    ip = x_forwarded_for.split(",")[0].strip()
                    instance.consent_ip_address = ip[:45]  # Max IPv6 length
                else:
                    remote_addr = request.META.get("REMOTE_ADDR", "")
                    instance.consent_ip_address = remote_addr[:45]

                # Get the user agent
                # Limit user agent length to prevent potential issues
                user_agent = request.META.get("HTTP_USER_AGENT", "")
                instance.consent_user_agent = user_agent[:500]

        # Update the instance with the validated data
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance
