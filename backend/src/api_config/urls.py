"""
URL configuration for api_config project.
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    # path('api/packages/', include('src.packages.urls')),
    # path('api/metrics/', include('src.metrics.urls')),
    # path('api/auth/', include('src.users.urls')),
    path('api/health/', include('src.health.urls')),
    # path('api/lineage/', include('src.lineage.urls')),
    # OpenAPI schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

