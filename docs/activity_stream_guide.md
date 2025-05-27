# Django Activity Stream with User Consent Guide

## Overview

This guide explains how to use the Django Activity Stream integration with user consent in your DataExchange application. The integration allows you to track user activities across the application while respecting user privacy by requiring explicit consent.

## Features

- User consent management for activity tracking
- Activity tracking for key models (Dataset, Organization, Resource, UseCase)
- API endpoints for retrieving activity streams
- Decorators for easily adding activity tracking to views
- Middleware for respecting user consent

## Consent Configuration

The activity stream integration can be configured through settings to control how consent is handled. The following settings are available in `settings.py`:

```python
# Activity Stream Consent Settings
ACTIVITY_CONSENT = {
    # If True, user consent is required for activity tracking
    # If False, consent is assumed and all activities are tracked
    'REQUIRE_CONSENT': env.bool('ACTIVITY_REQUIRE_CONSENT', default=True),

    # Default consent setting for new users
    'DEFAULT_CONSENT': env.bool('ACTIVITY_DEFAULT_CONSENT', default=False),

    # If True, anonymous activities are tracked (when consent is not required)
    'TRACK_ANONYMOUS': env.bool('ACTIVITY_TRACK_ANONYMOUS', default=False),

    # Maximum age of activities to keep (in days, 0 means keep forever)
    'MAX_AGE_DAYS': env.int('ACTIVITY_MAX_AGE_DAYS', default=0),
}
```

You can control these settings through environment variables or by modifying the settings directly.

### User Consent Management

When `REQUIRE_CONSENT` is set to `True`, the system requires explicit user consent before tracking activities. The system includes:

- `UserConsent` model for storing user consent preferences
- API endpoints for managing consent
- Middleware that checks consent before recording activities

### Consent API Endpoints

- `GET /auth/user/consent/` - Get the current user's consent settings
- `PUT /auth/user/consent/` - Update the current user's consent settings

Example request to update consent:

```json
{
  "activity_tracking_enabled": true
}
```

## Activity Tracking

There are several ways to track activities in your application:

### 1. Using Signal Handlers (Automatic Tracking)

The system includes signal handlers that automatically track common activities:

- Dataset creation, updates
- Organization creation, updates
- Resource creation, updates, downloads
- UseCase creation, updates

These are defined in `api/signals/activity_signals.py` and are automatically registered when the application starts.

### 2. Using Direct Function Calls

You can directly call tracking functions from your views or services:

```python
from api.activities.main import track_dataset_created

# In your view or service
track_dataset_created(user, dataset, request)
```

All tracking functions are imported and re-exported from `api.activities.main` for convenience.

### 3. Using the Decorator

For simple view functions, you can use the `track_activity` decorator:

```python
from api.activities.decorators import track_activity

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@track_activity(
    verb='viewed',
    get_action_object=lambda request, dataset_id, **kwargs: Dataset.objects.get(id=dataset_id),
    get_data=lambda request, dataset_id, **kwargs: {'dataset_id': str(dataset_id)}
)
def view_dataset_details(request, dataset_id):
    # Your view logic here
    pass
```

## Retrieving Activity Streams

The system provides several API endpoints for retrieving activity streams:

- `GET /activities/user/` - Get the current user's activity stream
- `GET /activities/global/` - Get the global activity stream
- `GET /activities/dataset/<uuid:dataset_id>/` - Get a dataset's activity stream
- `GET /activities/organization/<str:organization_id>/` - Get an organization's activity stream
- `GET /activities/resource/<uuid:resource_id>/` - Get a resource's activity stream
- `GET /activities/usecase/<int:usecase_id>/` - Get a use case's activity stream

You can also use the utility functions in `api/activities/display.py` to retrieve and format activity streams in your own views.

## Best Practices

1. **Always respect user consent**: Never track activities for users who haven't given consent.
2. **Be transparent**: Clearly explain to users what activities are being tracked and why.
3. **Use meaningful verbs**: Choose clear, descriptive verbs for activities (e.g., 'created', 'updated', 'viewed', 'downloaded').
4. **Include relevant context**: When tracking activities, include enough context to make the activity meaningful.
5. **Clean up old activities**: Consider implementing a cleanup task to remove old activities after a certain period.

## Example Implementation

See `api/views/example_activity_view.py` for examples of how to use the activity tracking decorator in your views.

For an example of direct function calls, see the resource download tracking in `api/views/download_view.py`.

## Troubleshooting

- **Activities not being recorded**: Check if the user has given consent and if the consent middleware is properly installed.
- **Consent not being respected**: Ensure that the `ActivityConsentMiddleware` is included in your middleware settings.
- **Signal handlers not working**: Make sure the signals are properly registered in `api/signals/__init__.py`.

## Extending the System

To track activities for new models:

1. Create tracking functions in a new module under `api/activities/`
2. Register the model with activity stream in `authorization/activity_registry.py`
3. Add signal handlers in `api/signals/activity_signals.py` if needed
4. Import and re-export the tracking functions in `api/activities/main.py`
