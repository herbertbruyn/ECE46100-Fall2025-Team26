import os
import re
import sys
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .auth import require_auth, require_admin

# Import base helpers
BASE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if BASE_SRC not in sys.path:
    sys.path.insert(0, BASE_SRC)

try:
    from lib.HuggingFace_API_Manager import HuggingFaceAPIManager
except Exception:
    HuggingFaceAPIManager = None

try:
    from lib.Github_API_Manager import GitHubAPIManager
except Exception:
    GitHubAPIManager = None

# Import models
from .models import Artifact, Dataset, Code, ModelRating

from .serializers import ArtifactCreateSerializer, ArtifactRegexSerializer

# Import the ingest service
try:
    from .services.ingest import IngestService
except ImportError:
    # Fallback if service not found
    IngestService = None

# Initialize clients
hf = HuggingFaceAPIManager() if HuggingFaceAPIManager else None
gh = GitHubAPIManager(token=os.getenv("GITHUB_TOKEN")) if GitHubAPIManager else None

# Initialize ingest service
ingest_service = IngestService() if IngestService else None

############################### Helper Functions ######################################
def derive_name(artifact_type: str, url: str) -> str:
    """Derive artifact name from URL"""
    try:
        if artifact_type == "model" and hf:
            return hf.model_link_to_id(url)
        if artifact_type == "dataset" and hf:
            return hf.dataset_link_to_id(url)
        if artifact_type == "code" and gh:
            owner, repo = gh.code_link_to_repo(url)
            return repo
    except Exception:
        pass
    return (url.rstrip("/").split("/")[-1] or "unnamed")[:255]

###################################### API Views ######################################
@api_view(["DELETE"])
# @require_admin
def reset_registry(request):
    """DELETE /reset - Reset registry to default state"""
    # Perform reset
    try:
        with transaction.atomic():
            # Count before deletion
            counts = {
                'artifacts': Artifact.objects.count(),
                'ratings': ModelRating.objects.count(),
                'datasets': Dataset.objects.count(),
                'code_repos': Code.objects.count(),
            }
            
            # Delete files
            deleted_files = 0
            for artifact in Artifact.objects.all():
                if artifact.blob:
                    artifact.blob.delete(save=False)
                    deleted_files += 1
            
            # Delete database records
            ModelRating.objects.all().delete()
            Artifact.objects.all().delete()
            Dataset.objects.all().delete()
            Code.objects.all().delete()
        
        return Response({
            "detail": "Registry is reset",
            "deleted": {**counts, "files": deleted_files}
        }, status=200)
        
    except Exception as e:
        return Response({"detail": f"Reset failed: {str(e)}"}, status=500)

@api_view(["GET"])
def health(request):
    """Simple readiness/liveness endpoint"""
    return Response({"status": "ok"}, status=200)

@api_view(["POST"])
@require_auth
def artifact_create(request, artifact_type: str):
    """
    POST /artifact/{artifact_type}
    
    Compute all metrics at upload time
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
    
    if not ingest_service:
        return Response(
            {"detail": "Ingest service not available"},
            status=500
        )
    
    # Use ingest service
    status_code, response_data = ingest_service.ingest_artifact(
        source_url=url,
        artifact_type=artifact_type,
        revision=request.data.get("revision", "main"),
        uploaded_by=request.user
    )
    
    return Response(response_data, status=status_code)


@api_view(["GET", "PUT", "DELETE"])
@require_auth
def artifact_details(request, artifact_type: str, id: int):
    """GET, PUT, DELETE /artifacts/{artifact_type}/{id}"""
    obj = get_object_or_404(Artifact, pk=id, type=artifact_type)
    # Retrieve artifact details
    if request.method == "GET":
    
        response_data = {
            "metadata": obj.metadata_view(),
            "data": {
                "url": obj.source_url,
                "download_url": obj.blob.url if obj.blob else None
            }
        }
        
        return Response(response_data, status=200)
    
    # Update artifact (re-ingest)
    elif request.method == "PUT":
    
        # Validate metadata matches
        metadata = request.data.get("metadata", {})
        if metadata.get("id") != id:
            return Response(
                {"detail": "ID mismatch"},
                status=400
            )
        
        # Get new URL
        new_url = request.data.get("data", {}).get("url")
        if not new_url:
            return Response({"detail": "Missing URL in data"}, status=400)
        
        if not ingest_service:
            return Response(
                {"detail": "Ingest service not available"},
                status=500
            )
        
        # Delete old artifact and re-ingest
        obj.delete()
        
        status_code, response_data = ingest_service.ingest_artifact(
            source_url=new_url,
            artifact_type=artifact_type,
            uploaded_by=request.user
        )
        
        if status_code == 201:
            return Response({"detail": "Artifact is updated."}, status=200)
        else:
            return Response(response_data, status=status_code)

    # Delete artifact
    elif request.method == "DELETE":
    
        # Delete file from storage
        if obj.blob:
            obj.blob.delete(save=False)
        
        # Delete from database (cascade will delete rating)
        obj.delete()
        
        return Response({"detail": "Artifact is deleted."}, status=200)


@api_view(["GET"])
@require_auth
def model_rate(request, id: int):
    """
    GET /artifact/model/{id}/rate
    
    Fast database lookup (Option 2)
    """
    obj = get_object_or_404(Artifact, pk=id, type="model")
    
    # Check if rating exists
    if not hasattr(obj, 'rating'):
        # Check status for helpful message
        if hasattr(obj, 'status'):
            if obj.status == "pending":
                return Response(
                    {"detail": "Artifact is being processed, rating not yet available"},
                    status=404
                )
            elif obj.status == "rating":
                return Response(
                    {"detail": "Artifact is being rated, please try again shortly"},
                    status=404
                )
            elif obj.status == "rejected":
                return Response(
                    {"detail": "Artifact was rejected during rating"},
                    status=404
                )
        
        return Response(
            {"detail": "Rating not available for this artifact"},
            status=404
        )
    
    # Fast database lookup!
    return Response(obj.rating.to_dict(), status=200)


@api_view(["POST"])
@require_auth
def artifact_by_regex(request):
    """POST /artifact/byRegEx"""
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


@api_view(["POST"])
@require_auth
def artifacts_list(request):
    """POST /artifacts"""
    queries = request.data
    if not isinstance(queries, list):
        return Response(
            {"detail": "Request body must be an array of queries"},
            status=400
        )
    
    results = []
    for query in queries:
        name = query.get("name", "*")
        artifact_type = query.get("type")
        
        if name == "*":
            # Return all artifacts with completed status if available
            if Artifact._meta.get_field('status'):
                qs = Artifact.objects.filter(status="completed")
            else:
                qs = Artifact.objects.all()
        else:
            if Artifact._meta.get_field('status'):
                qs = Artifact.objects.filter(name__icontains=name, status="completed")
            else:
                qs = Artifact.objects.filter(name__icontains=name)
        
        if artifact_type:
            qs = qs.filter(type=artifact_type)
        
        results.extend([a.metadata_view() for a in qs])
    
    # Pagination
    offset = request.query_params.get("offset", 0)
    try:
        offset = int(offset)
    except ValueError:
        offset = 0
    
    page_size = 100
    paginated = results[offset:offset + page_size]
    
    response = Response(paginated, status=200)
    if len(results) > offset + page_size:
        response["offset"] = str(offset + page_size)
    
    return response


@api_view(["GET"])
@require_auth
def artifact_cost(request, artifact_type: str, id: int):
    """GET /artifact/{artifact_type}/{id}/cost"""
    obj = get_object_or_404(Artifact, pk=id, type=artifact_type)
    
    include_dependencies = request.query_params.get("dependency", "false").lower() == "true"
    
    if include_dependencies and artifact_type == "model" and hasattr(obj, 'dataset') and hasattr(obj, 'code'):
        # Calculate total cost including dependencies
        standalone_cost = obj.size_bytes / (1024 * 1024)  # Convert to MB
        total_cost = standalone_cost
        
        # Add dataset size if present
        if obj.dataset:
            dataset_artifact = Artifact.objects.filter(
                type="dataset",
                name=obj.dataset.name,
                status="completed" if hasattr(Artifact, 'status') else None
            ).first()
            if dataset_artifact:
                total_cost += dataset_artifact.size_bytes / (1024 * 1024)
        
        # Add code size if present
        if obj.code:
            code_artifact = Artifact.objects.filter(
                type="code",
                name=obj.code.name,
                status="completed" if hasattr(Artifact, 'status') else None
            ).first()
            if code_artifact:
                total_cost += code_artifact.size_bytes / (1024 * 1024)
        
        return Response({
            str(id): {
                "standalone_cost": round(standalone_cost, 2),
                "total_cost": round(total_cost, 2)
            }
        }, status=200)
    else:
        # Just standalone cost
        cost_mb = obj.size_bytes / (1024 * 1024)
        return Response({
            str(id): {
                "total_cost": round(cost_mb, 2)
            }
        }, status=200)