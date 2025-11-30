# api/urls.py
from django.urls import path, re_path
from . import views

urlpatterns = [
    # Admin reset endpoint
    path("reset", views.reset_registry),

    # Health
    path("health", views.health),
    
    # Auth (not implemented)
    path("authenticate", views.authenticate),
    
    # Artifact operations
    path("artifact/byRegEx", views.artifact_by_regex),
    re_path(
        r"^artifact/(?P<artifact_type>(model|dataset|code))$",
        views.artifact_create
    ),
    re_path(
        r"^artifacts/(?P<artifact_type>(model|dataset|code))/(?P<id>\d+)$",
        views.artifact_details
    ),
    
    # Rating endpoint
    path("artifact/model/<int:id>/rate", views.model_rate),
    
    # List endpoint
    path("artifacts", views.artifacts_list),
    
    # Cost endpoint
    re_path(
        r"^artifact/(?P<artifact_type>(model|dataset|code))/(?P<id>\d+)/cost$",
        views.artifact_cost
    ),
]