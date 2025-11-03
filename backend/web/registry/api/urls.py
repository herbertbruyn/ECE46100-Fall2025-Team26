from django.urls import path, re_path
from . import views

urlpatterns = [
    path("health", views.health),                                  # GET
    path("authenticate", views.authenticate),                      # PUT -> 501
    path("artifact/byRegEx", views.artifact_by_regex),             # POST
    re_path(r"^artifact/(?P<artifact_type>(model|dataset|code))$", views.artifact_create), # POST
    re_path(r"^artifacts/(?P<artifact_type>(model|dataset|code))/(?P<id>\d+)$", views.artifact_get), # GET
    re_path(r"^artifacts/(?P<artifact_type>(model|dataset|code))/(?P<id>\d+)/lineage$", views.artifact_lineage), # GET
]