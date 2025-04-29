"""DataSpace URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from typing import List, Union, cast

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

from api.views import health

# Type alias for URL patterns
URLPatternsList = List[Union[URLPattern, URLResolver]]

# API Documentation
schema_view = get_schema_view(
    openapi.Info(
        title="DataEx API",
        default_version="v1",
        description="DataEx Backend API Documentation",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@dataex.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[],
)

urlpatterns: URLPatternsList = [
    path("api/", include("api.urls")),
    path("auth/", include("authorization.urls")),
    path("admin/", admin.site.urls),
    # Health check endpoint
    path("health/", health.health_check, name="health_check"),
    # API documentation
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# In debug mode, add static URL patterns and debug toolbar
if settings.DEBUG:
    # Add static URL patterns for development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Add debug toolbar
    import debug_toolbar  # type: ignore[import]

    debug_patterns: URLPatternsList = [
        path("__debug__/", include(debug_toolbar.urls)),
    ]
    urlpatterns = debug_patterns + cast(URLPatternsList, urlpatterns)

    # In debug mode, explicitly serve admin static files
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
