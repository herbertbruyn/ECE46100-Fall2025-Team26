from django.shortcuts import render

import os
import re
import sys
import logging
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

# 1) Make backend/src folder importable
BASE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if BASE_SRC not in sys.path:
    sys.path.insert(0, BASE_SRC)

# 2) Try to import helpers; if they're missing or error, fall back safely
try:
    from lib.HuggingFace_API_Manager import HuggingFaceAPIManager
except Exception:
    HuggingFaceAPIManager = None

try:
    from lib.Github_API_Manager import GitHubAPIManager
except Exception:
    GitHubAPIManager = None

from .models import Artifact
from .serializers import ArtifactCreateSerializer, ArtifactRegexSerializer

# 3) Create clients if available (allow running without tokens)
hf = HuggingFaceAPIManager() if HuggingFaceAPIManager else None
gh = GitHubAPIManager(token=os.getenv("GITHUB_TOKEN")) if GitHubAPIManager else None

@api_view(["GET"])
def health(request):
    """Simple readiness/liveness endpoint."""
    return Response({"status": "ok"}, status=200)

@api_view(["PUT"])
def authenticate(request):
    """
    MVP path per the OpenAPI: returning 501 is allowed.
    This lets us ignore X-Authorization for other endpoints until you add auth later.
    """
    return Response({"detail": "Not implemented"}, status=501)

def derive_name(artifact_type: str, url: str) -> str:
    """
    Use your helpers to turn a URL into a human-readable stable name.
    If anything goes wrong (helper missing, bad URL), fallback to last path segment.
    """
    try:
        if artifact_type == "model" and hf:
            # e.g., "google-bert/bert-base-uncased"
            return hf.model_link_to_id(url)
        if artifact_type == "dataset" and hf:
            # e.g., "xlangai/AgentNet"
            return hf.dataset_link_to_id(url)
        if artifact_type == "code" and gh:
            # returns (owner, repo)
            owner, repo = gh.code_link_to_repo(url)
            return repo
    except Exception:
        # keep the API resilient for MVP
        pass
    # fallback: last URL token
    return (url.rstrip("/").split("/")[-1] or "unnamed")[:255]

@api_view(["POST"])
def artifact_create(request, artifact_type: str):
    """
    POST /artifact/{artifact_type}
    Body: {"url":"https://..."}
    Returns: 201 with Artifact {metadata:{id,name,type}, data:{url}}
             409 if duplicate
             400 if bad body
             400 if artifact_type invalid
    """
    if artifact_type not in ("model", "dataset", "code"):
        return Response({"detail": "invalid artifact_type"}, status=400)

    ser = ArtifactCreateSerializer(data=request.data)
    if not ser.is_valid():
        return Response(
            {"detail": "There is missing field(s) in the artifact_data or it is formed improperly."},
            status=400,
        )

    url = ser.validated_data["url"]
    name = derive_name(artifact_type, url)

    # unique_together ensures we detect duplicates
    obj, created = Artifact.objects.get_or_create(
        name=name, type=artifact_type, source_url=url
    )

    # Lineage info
    if created and artifact_type == "model" and hf:
        try:
            model_id = hf.model_link_to_id(url)
            config = hf.get_model_config(model_id)
            
            if config:
                obj.config_metadata = config
                parent_id = hf.extract_parent_model(config)
                
                if parent_id:
                    logging.info(f"Found parent model {parent_id} for {name}")
                    # Create parent artifact if it doesn't exist
                    parent_url = f"https://huggingface.co/{parent_id}"
                    parent_name = parent_id.split('/')[-1]
                    
                    parent, _ = Artifact.objects.get_or_create(
                        name=parent_name,
                        type="model",
                        defaults={"source_url": parent_url}
                    )
                    obj.parents.add(parent)
                
                obj.save()
        except Exception as e:
            logging.warning(f"Could not extract lineage for {name}: {e}")
    
    if not created:
        return Response({"detail": "Artifact exists already."}, status=409)

    return Response(obj.to_artifact_view(), status=201)

@api_view(["GET"])
def artifact_get(request, artifact_type: str, id: int):
    """
    GET /artifacts/{artifact_type}/{id}
    Returns: 200 with the Artifact object
             404 if not found (Django auto-handled by get_object_or_404)
    """
    obj = get_object_or_404(Artifact, pk=id, type=artifact_type)
    return Response(obj.to_artifact_view(), status=200)

@api_view(["POST"])
def artifact_by_regex(request):
    """
    POST /artifact/byRegEx
    Body: {"regex":"..."}
    Returns: 200 with [ArtifactMetadata,...]
             400 invalid body or regex
             404 if no matches
    """
    ser = ArtifactRegexSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"detail": "invalid regex"}, status=400)

    pattern = ser.validated_data["regex"]
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return Response({"detail": "invalid regex"}, status=400)

    results = [a.metadata_view() for a in Artifact.objects.all() if rx.search(a.name)]
    if not results:
        return Response({"detail": "No artifact found under this regex."}, status=404)
    return Response(results, status=200)

@api_view(["GET"])
def artifact_lineage(request, artifact_type: str, id: int):
    """
    GET /artifacts/{artifact_type}/{id}/lineage
    Returns: 200 with the lineage graph
             404 if not found (Django auto-handled by get_object_or_404)
    """
    obj = get_object_or_404(Artifact, pk=id, type=artifact_type)
    lineage = obj.get_lineage_graph()
    return Response(lineage, status=200)

