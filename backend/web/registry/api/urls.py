# api/urls.py
from django.urls import path, re_path
from . import views, auth_views

urlpatterns = [
    # Admin reset endpoint
    path("reset", views.reset_registry),

    # Health
    path("health", views.health),
    
    # Auth (not implemented)
    path("authenticate", auth_views.authenticate),
    
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
    
    # Tracks endpoint
    path("tracks", views.tracks),
    
    # Cost endpoint
    re_path(
        r"^artifact/(?P<artifact_type>(model|dataset|code))/(?P<id>\d+)/cost$",
        views.artifact_cost
    ),

    # Lineage endpoint
    path("artifact/model/<int:id>/lineage", views.artifact_lineage)
]