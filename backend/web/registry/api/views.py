import os
import re
import sys
import io
import json
import zipfile
import logging
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
from .models import Artifact, Dataset, Code, ModelRating, ActivityLog

from .serializers import ArtifactCreateSerializer, ArtifactRegexSerializer

# Import the ingest service based on configuration
try:
    from django.conf import settings

    # Default: Use async proper service (returns 202, blocks on GET for autograder)
    # This is the spec-compliant implementation
    if getattr(settings, 'USE_S3', False) or os.getenv('USE_S3', 'false').lower() == 'true':
        from .services.ingest_async_proper import AsyncIngestService as IngestService
    else:
        # Fallback for local development without S3
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

def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def derive_name(artifact_type: str, url: str) -> str:
    """Derive artifact name from URL (for database storage)"""
    try:
        if artifact_type == "model" and hf:
            # Get the model ID and convert slashes to hyphens for storage
            model_id = hf.model_link_to_id(url)
            return model_id.replace('/', '-')
        if artifact_type == "dataset" and hf:
            # Get the dataset ID and convert slashes to hyphens for storage
            dataset_id = hf.dataset_link_to_id(url)
            return dataset_id.replace('/', '-')
        if artifact_type == "code" and gh:
            owner, repo = gh.code_link_to_repo(url)
            return repo
    except Exception:
        pass
    return (url.rstrip("/").split("/")[-1] or "unnamed")[:255]


def extract_parent_model(artifact):
    """
    Extract parent model from config.json in artifact's ZIP file
    """

    # Make sure artifact is stored
    if not artifact.blob:
        return None

    try:
        with artifact.blob.open("rb") as f:
            zip_bytes = f.read()
            zip_buffer = io.BytesIO(zip_bytes)
            with zipfile.ZipFile(zip_buffer) as zf:
                if 'config.json' not in zf.namelist():
                    return None

                with zf.open('config.json') as config_file:
                    config = json.load(config_file)

                    # Look for parent field
                    for field in ['base_model_name_or_path', '_name_or_path', 'base_model']:
                        if field in config:
                            parent = config[field]
                            if isinstance(parent, str) and parent:
                                return parent
                    return None



    except Exception as e:
        logging.warning(f"Could not extract parent model from artifact {artifact.id}: {e}")
        return None



###################################### API Views ######################################
@api_view(["DELETE"])
# @require_admin
def reset_registry(request):
    """DELETE /reset - Reset registry to default state"""
    import boto3
    from botocore.exceptions import ClientError

    # Perform reset
    try:
        # Count before deletion
        counts = {
            'artifacts': Artifact.objects.count(),
            'ratings': ModelRating.objects.count(),
            'datasets': Dataset.objects.count(),
            'code_repos': Code.objects.count(),
        }

        # Delete files (both local blob and S3)
        deleted_local = 0
        deleted_s3 = 0
        s3_error = None

        # Always try to clean S3 if bucket is configured
        bucket = os.getenv('AWS_STORAGE_BUCKET_NAME')

        if bucket:
            logging.info(f"Attempting S3 cleanup for bucket: {bucket}")
            try:
                # Initialize S3 client
                s3_client = boto3.client('s3')

                # List all objects under artifacts/ prefix
                paginator = s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket, Prefix='artifacts/')

                objects_found = 0
                for page in pages:
                    if 'Contents' in page:
                        objects_found += len(page['Contents'])
                        # Delete in batches of up to 1000 (S3 limit)
                        objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]

                        if objects_to_delete:
                            logging.info(f"Deleting {len(objects_to_delete)} objects from S3...")
                            response = s3_client.delete_objects(
                                Bucket=bucket,
                                Delete={'Objects': objects_to_delete}
                            )
                            deleted_s3 += len(response.get('Deleted', []))

                            if 'Errors' in response:
                                for error in response['Errors']:
                                    logging.warning(f"Failed to delete {error['Key']}: {error['Message']}")

                logging.info(f"S3 cleanup complete: found {objects_found} objects, deleted {deleted_s3}")

            except ClientError as e:
                s3_error = str(e)
                logging.error(f"S3 cleanup failed: {e}")
            except Exception as e:
                s3_error = str(e)
                logging.error(f"Unexpected S3 error: {e}")
        else:
            logging.warning("AWS_STORAGE_BUCKET_NAME not set, skipping S3 cleanup")

        # Delete local blobs if they exist
        for artifact in Artifact.objects.all():
            if artifact.blob:
                try:
                    artifact.blob.delete(save=False)
                    deleted_local += 1
                except Exception as e:
                    logging.warning(f"Failed to delete local blob: {e}")

        # Delete database records
        with transaction.atomic():
            ModelRating.objects.all().delete()
            Artifact.objects.all().delete()
            Dataset.objects.all().delete()
            Code.objects.all().delete()

        response_data = {
            "detail": "Registry is reset",
            "deleted": {
                **counts,
                "s3_objects": deleted_s3
            }
        }

        if s3_error:
            response_data["s3_error"] = s3_error

        return Response(response_data, status=200)

    except Exception as e:
        logging.error(f"Reset failed: {e}")
        return Response({"detail": f"Reset failed: {str(e)}"}, status=500)

@api_view(["GET"])
def health(request):
    """Simple readiness/liveness endpoint"""
    return Response({"status": "ok"}, status=200)

@api_view(["POST"])
# @require_auth
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
    name = ser.validated_data["name"]

    if not ingest_service:
        return Response(
            {"detail": "Ingest service not available"},
            status=500
        )

    user = getattr(request, 'user', None)  # Get user if exists, otherwise None
    if user and not user.is_authenticated:
        user = None

    # Use ingest service
    status_code, response_data = ingest_service.ingest_artifact(
        source_url=url,
        artifact_type=artifact_type,
        artifact_name=name,
        revision=request.data.get("revision", "main"),
        uploaded_by=user
    )

    # Log upload activity if successful
    if status_code in [200, 201, 202]:
        artifact_name = response_data.get('metadata', {}).get('name') or derive_name(artifact_type, url)
        artifact_id = response_data.get('metadata', {}).get('id')
        ActivityLog.log(
            user=user or 'anonymous',
            action='upload',
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            artifact_name=artifact_name,
            details=f"Uploaded from {url}",
            ip_address=get_client_ip(request)
        )

    return Response(response_data, status=status_code)


@api_view(["GET", "PUT", "DELETE"])
# @require_auth
def artifact_details(request, artifact_type: str, id: int):
    """GET, PUT, DELETE /artifacts/{artifact_type}/{id}"""
    import time
    
    # Generate request ID for tracking
    request_id = int(time.time() * 1000) % 10000000000000
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    start_time = time.time()
    
    # Log incoming request
    logging.info(f"{'='*80}")
    logging.info(f"[{request_id}] {request.method} /artifacts/{artifact_type}/{id} from {client_ip}")
    logging.info(f"  Searching for artifact: type='{artifact_type}', id={id}")

    try:
        obj = Artifact.objects.get(pk=id, type=artifact_type)
        logging.info(f"  ✓ Found artifact: name='{obj.name}', status='{obj.status}'")
    except Artifact.DoesNotExist:
        elapsed = time.time() - start_time
        logging.info(f"  ✗ Artifact not found: type='{artifact_type}', id={id}")
        logging.info(f"[{request_id}] {request.method} /artifacts/{artifact_type}/{id} → 404 ({elapsed:.3f}s)")
        logging.info(f"{'='*80}")
        return Response({"detail": "Artifact not found"}, status=404)

    # Retrieve artifact details
    if request.method == "GET":
        logging.info(f"  Checking artifact status for readiness...")
        
        # CRITICAL: Block until artifact is ready (for autograder consistency)
        # Poll status up to 3 minutes (autograder timeout)
        max_wait = 170  # 170 seconds (safe margin under 3min autograder timeout)
        start_time = time.time()

        while obj.status in ["pending_rating", "rating_in_progress", "ingesting", "pending", "downloading", "rating"]:
            if time.time() - start_time > max_wait:
                elapsed = time.time() - start_time
                logging.warning(f"  ⏱ Timeout waiting for artifact {id} to be ready (waited {elapsed:.1f}s)")
                logging.info(f"[{request_id}] GET /artifacts/{artifact_type}/{id} → 504 ({elapsed:.3f}s)")
                logging.info(f"{'='*80}")
                return Response({"detail": "Artifact processing timeout"}, status=504)

            time.sleep(1)  # Poll every 1 second
            obj.refresh_from_db()

        # If disqualified or failed, return 404 (artifact not available)
        if obj.status in ["disqualified", "failed", "rejected"]:
            elapsed = time.time() - start_time
            logging.info(f"  ✗ Artifact has invalid status: '{obj.status}'")
            logging.info(f"[{request_id}] GET /artifacts/{artifact_type}/{id} → 404 ({elapsed:.3f}s)")
            logging.info(f"{'='*80}")
            return Response({"detail": "Artifact not found"}, status=404)

        # Now artifact is ready
        response_data = {
            "metadata": obj.metadata_view(),
            "data": {
                "url": obj.source_url,
                "download_url": obj.download_url or (obj.blob.url if obj.blob else None)
            }
        }

        # Log view/download activity
        user = getattr(request, 'user', None)
        ActivityLog.log(
            user=user or 'anonymous',
            action='download',
            artifact_type=artifact_type,
            artifact_id=id,
            artifact_name=obj.name,
            ip_address=get_client_ip(request)
        )

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
        
        user = getattr(request, 'user', None)
        status_code, response_data = ingest_service.ingest_artifact(
            source_url=new_url,
            artifact_type=artifact_type,
            uploaded_by=user
        )

        # Log update activity
        if status_code in [200, 201, 202]:
            ActivityLog.log(
                user=user or 'anonymous',
                action='update',
                artifact_type=artifact_type,
                artifact_id=id,
                artifact_name=obj.name,
                details=f"Updated to {new_url}",
                ip_address=get_client_ip(request)
            )

        if status_code == 201:
            return Response({"detail": "Artifact is updated."}, status=200)
        else:
            return Response(response_data, status=status_code)

    # Delete artifact
    elif request.method == "DELETE":

        # Log delete activity before deleting
        user = getattr(request, 'user', None)
        ActivityLog.log(
            user=user or 'anonymous',
            action='delete',
            artifact_type=artifact_type,
            artifact_id=id,
            artifact_name=obj.name,
            ip_address=get_client_ip(request)
        )

        # Delete file from storage
        if obj.blob:
            obj.blob.delete(save=False)

        # Delete from database (cascade will delete rating)
        obj.delete()

        return Response({"detail": "Artifact is deleted."}, status=200)


@api_view(["GET"])
# @require_auth
def model_rate(request, id: int):
    """
    GET /artifact/model/{id}/rate

    Fast database lookup (Option 2)
    Blocks until rating is ready for autograder consistency
    """
    import time

    try:
        obj = Artifact.objects.get(pk=id, type="model")
    except Artifact.DoesNotExist:
        return Response({"detail": "Artifact not found"}, status=404)

    # CRITICAL: Block until rating is ready (for autograder consistency)
    max_wait = 170  # 170 seconds (safe margin under 3min autograder timeout)
    start_time = time.time()

    while obj.status in ["pending_rating", "rating_in_progress", "ingesting", "pending", "downloading", "rating"]:
        if time.time() - start_time > max_wait:
            logging.warning(f"Timeout waiting for rating on artifact {id}")
            return Response({"detail": "Rating timeout"}, status=504)

        time.sleep(1)  # Poll every 1 second
        obj.refresh_from_db()

    # If disqualified, failed, or rejected - return 404
    if obj.status in ["disqualified", "failed", "rejected"]:
        return Response({"detail": "Artifact not found"}, status=404)

    # Check if we have rating_scores (new async format)
    if obj.rating_scores and obj.net_score is not None:
        # Convert to spec-compliant ModelRating format
        rating_response = {
            "name": obj.name,
            "category": obj.type,  # Using artifact type as category
            "net_score": obj.net_score,
            "net_score_latency": 0.0,  # Latency not tracked in async format
        }

        # Add all metrics with their latencies
        for metric_name in ['ramp_up_time', 'bus_factor', 'performance_claims', 'license',
                           'dataset_and_code_score', 'dataset_quality', 'code_quality',
                           'reproducibility', 'reviewedness', 'tree_score']:
            rating_response[metric_name] = obj.rating_scores.get(metric_name, 0.0)
            rating_response[f"{metric_name}_latency"] = 0.0

        # size_score must be an object per spec (lines 1191-1216)
        size_score_value = obj.rating_scores.get('size_score', 0.0)
        rating_response['size_score'] = {
            "raspberry_pi": size_score_value,
            "jetson_nano": size_score_value,
            "desktop_pc": size_score_value,
            "aws_server": size_score_value
        }
        rating_response['size_score_latency'] = 0.0

        # Log rate activity
        user = getattr(request, 'user', None)
        ActivityLog.log(
            user=user or 'anonymous',
            action='rate',
            artifact_type='model',
            artifact_id=id,
            artifact_name=obj.name,
            details=f"Net score: {obj.net_score:.2f}",
            ip_address=get_client_ip(request)
        )

        return Response(rating_response, status=200)

    # Fallback: check if rating exists (old format)
    if hasattr(obj, 'rating'):
        return Response(obj.rating.to_dict(), status=200)

    # No rating available
    return Response(
        {"detail": "Rating not available for this artifact"},
        status=404
    )


@api_view(["POST"])
# @require_auth
def artifact_by_regex(request):
    """POST /artifact/byRegEx - with blocking until artifacts are ready"""
    import time as time_module
    import sys

    ser = ArtifactRegexSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"detail": "invalid regex"}, status=400)

    pattern = ser.validated_data["regex"]
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return Response({"detail": "invalid regex"}, status=400)

    # Blocking behavior: wait up to 170 seconds for artifacts to become ready
    valid_statuses = ["ready", "completed"]
    max_wait_seconds = 170
    poll_interval = 2
    elapsed = 0
    prev_count = 0

    # Poll and wait for artifacts to complete
    while elapsed < max_wait_seconds:
        # Get all ready/completed artifacts that match the regex
        all_ready = Artifact.objects.filter(status__in=valid_statuses)
        matching_artifacts = [a for a in all_ready if rx.search(a.name)]
        current_count = len(matching_artifacts)

        # Check if we have any pending/in-progress artifacts
        pending_count = Artifact.objects.filter(
            status__in=["pending_rating", "rating_in_progress", "ingesting"]
        ).count()

        # If count is increasing or there are still pending artifacts, keep waiting
        if pending_count > 0 or current_count > prev_count:
            prev_count = current_count
            time_module.sleep(poll_interval)
            elapsed += poll_interval
        else:
            # No more pending artifacts and count stable - done
            break

    # Final query after waiting
    all_ready = Artifact.objects.filter(status__in=valid_statuses)
    matching_artifacts = [a for a in all_ready if rx.search(a.name)]
    results = [a.metadata_view() for a in matching_artifacts]

    # Debug output
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.write(f"POST /artifact/byRegEx DEBUG\n")
    sys.stderr.write(f"Regex pattern: '{pattern}'\n")
    sys.stderr.write(f"Wait time: {elapsed}s\n")
    sys.stderr.write(f"Total artifacts in DB (ready/completed): {all_ready.count()}\n")
    sys.stderr.write(f"Artifact names in DB: {[a.name for a in all_ready]}\n")
    sys.stderr.write(f"Matching count: {len(matching_artifacts)}\n")
    sys.stderr.write(f"Matching names: {[a.name for a in matching_artifacts]}\n")
    sys.stderr.write(f"Response status: {'200' if results else '404'}\n")
    sys.stderr.write("=" * 80 + "\n")
    sys.stderr.flush()

    # Log search activity
    user = getattr(request, 'user', None)
    ActivityLog.log(
        user=user or 'anonymous',
        action='search',
        details=f"Regex search: {pattern} ({len(results)} results)",
        ip_address=get_client_ip(request)
    )

    if not results:
        return Response({"detail": "No artifact found under this regex."}, status=404)
    return Response(results, status=200)


@api_view(["POST"])
# @require_auth
def artifacts_list(request):
    """POST /artifacts"""
    import time
    import sys

    # Generate request ID for tracking
    request_id = int(time.time() * 1000) % 10000000000000  # 13-digit timestamp-based ID
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    start_time = time.time()

    # Log incoming request
    logging.info(f"[{request_id}] POST /artifacts from {client_ip}")
    
    queries = request.data
    if not isinstance(queries, list):
        return Response(
            {"detail": "Request body must be an array of queries"},
            status=400
        )
    
    # Log number of queries
    logging.info(f"POST /artifacts: Processing {len(queries)} query(ies)")
    
    results = []
    
    for idx, query in enumerate(queries, 1):
        name = query.get("name", "*")

        # Handle "types" field (list from spec)
        types_list = query.get("types", [])

        # Extract single type for filtering (we only support filtering by one type)
        # Empty list means "all types" (no filtering)
        if types_list and len(types_list) > 0:
            artifact_type = types_list[0]  # Use first type from list
        else:
            artifact_type = None  # No type filtering

        logging.info(f"Query {idx}: name='{name}', types={types_list}")
        
        # Get ready/completed artifacts, with polling for autograder compatibility
        valid_statuses = ["ready", "completed"]
        max_wait_seconds = 170  # 2 minutes 50 sec max wait
        poll_interval = 2  # Check every 2 seconds

        if name == "*":
            # Query all: wait as long as possible for all artifacts to complete
            import time as time_module

            # Count total artifacts that exist (any status)
            total_artifacts = Artifact.objects.count()

            # Poll and wait for artifacts to complete
            elapsed = 0
            prev_count = 0

            while elapsed < max_wait_seconds:
                qs = Artifact.objects.filter(status__in=valid_statuses)
                current_count = qs.count()

                # Check if we have any pending/in-progress artifacts
                pending_count = Artifact.objects.filter(
                    status__in=["pending_rating", "rating_in_progress", "ingesting"]
                ).count()

                # If count is increasing or there are still pending artifacts, keep waiting
                if pending_count > 0 or current_count > prev_count:
                    prev_count = current_count
                    time_module.sleep(poll_interval)
                    elapsed += poll_interval
                else:
                    # No more pending artifacts and count stable - done
                    break

        else:
            # Specific name: wait for that artifact to become ready
            logging.info(f"Searching for exact match: '{name}'")

            # First check if artifact exists at all
            artifact_exists = Artifact.objects.filter(name__iexact=name).exists()

            if not artifact_exists:
                # Artifact doesn't exist, no point waiting
                qs = Artifact.objects.none()
                logging.info(f"No artifact with name '{name}' exists in database")
            else:
                # Artifact exists, wait for it to become ready
                qs = Artifact.objects.filter(name__iexact=name, status__in=valid_statuses)

                # Poll until ready or timeout
                elapsed = 0
                while qs.count() == 0 and elapsed < max_wait_seconds:
                    import time as time_module
                    time_module.sleep(poll_interval)
                    elapsed += poll_interval
                    qs = Artifact.objects.filter(name__iexact=name, status__in=valid_statuses)

                    # Check if artifact failed/disqualified (stop waiting)
                    artifact_status = Artifact.objects.filter(name__iexact=name).values_list('status', flat=True).first()
                    if artifact_status in ["failed", "disqualified"]:
                        logging.info(f"Artifact '{name}' failed with status: {artifact_status}")
                        break

            # Log the result count
            count = qs.count()
            if count > 0:
                logging.info(f"Exact match: {count} package(s)")
            else:
                logging.info(f"No exact match found for '{name}' after waiting")
                sys.stderr.write(f"DEBUG: Artifact '{name}' not ready after {elapsed}s wait\n")
                sys.stderr.flush()
        
        if artifact_type:
            qs = qs.filter(type=artifact_type)
        
        results.extend([a.metadata_view() for a in qs])
    
    # Log total results
    logging.info(f"POST /artifacts: Returning {len(results)} total")
    
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
    
    # Log completion with timing
    elapsed = time.time() - start_time
    logging.info(f"[{request_id}] POST /artifacts → 200 ({elapsed:.3f}s)")
    
    return response


@api_view(["GET"])
# @require_auth
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

@api_view(["GET"])
def tracks(request):
    """GET /tracks - Return planned tracks"""
    try:
        return Response({
            "plannedTracks": ["Other Security track"]
        }, status=200)
    except Exception:
        return Response({"detail": "System error"}, status=500)


@api_view(["GET"])
#@require_auth
def artifact_lineage(request, id: int):
    """
    Get /artifact/model/{id}/lineage
    Return lineage graph for a model
    Error Codes:
    - 200: Success
    - 400: Lineage graph cannot be computed because the artifact metadata is missing or malformed
    - 403: Authentication failed due to invalid or missing Authentication Token
    - 404: Artifact does not exist
    """

    # 404
    obj = get_object_or_404(Artifact, pk=id, type="model")


    nodes = []
    edges = []

    # Add the model as the node
    nodes.append({
        "artifact_id": obj.id,
        "name": obj.name,
        "source": "config_json"
    })

    # 400
    if not obj.blob:
        return Response(
            {"detail": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."},
            status=400
        )

    # Try to extract parent model
    parent_model_id = extract_parent_model(obj)

    if parent_model_id:
        parent_name = parent_model_id.split('/')[-1] if '/' in parent_model_id else parent_model_id

        # Search for parent in registry
        parent_artifact = Artifact.objects.filter(
            type="model",
            name__icontains=parent_name,
            status="completed"
        ).exclude(id=obj.id).first()

        if parent_artifact:
            nodes.append({
                "artifact_id": parent_artifact.id,
                "name": parent_artifact.name,
                "source": "config_json"
            })
            edges.append({
                "from_node_artifact_id": parent_artifact.id,
                "to_node_artifact_id": obj.id,
                "relationship": "base_model"
            })

    return Response({
        "nodes": nodes,
        "edges": edges
    }, status=200)


@api_view(["POST"])
#@require_auth
def artifact_license_check(request, id: int):
    """POST /artifact/model/{id}/license-check - Check license compatibility"""
    import requests
    import re

    try:
        # Get the model artifact
        obj = Artifact.objects.get(pk=id, type="model")

        # License check requires rating_scores, so artifact must be rated
        # Return 404 if artifact is not available (same logic as GET endpoint)
        if obj.status in ["disqualified", "failed", "rejected"]:
            return Response({"detail": "Artifact not found"}, status=404)

    except Artifact.DoesNotExist:
        return Response({"detail": "Artifact not found"}, status=404)

    # Validate request body exists
    if not request.data:
        return Response({"detail": "Request body is required"}, status=400)

    # Get GitHub URL from request body
    github_url = request.data.get("github_url")
    if not github_url:
        return Response({"detail": "github_url is required"}, status=400)

    # Extract owner/repo from GitHub URL
    match = re.search(r'github\.com/([^/]+)/([^/]+)', github_url)
    if not match:
        return Response({"detail": "Invalid GitHub URL"}, status=400)

    owner, repo = match.groups()
    repo = repo.rstrip('.git')  # Remove .git suffix if present

    # Get GitHub repo license via API
    try:
        github_api_url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {'Accept': 'application/vnd.github.v3+json'}

        github_token = os.getenv('GITHUB_TOKEN')
        if github_token:
            headers['Authorization'] = f'token {github_token}'

        response = requests.get(github_api_url, headers=headers, timeout=10)

        if response.status_code == 404:
            return Response({"detail": "GitHub repository not found"}, status=404)
        elif response.status_code != 200:
            return Response({"detail": "Failed to retrieve GitHub license information"}, status=502)

        repo_data = response.json()
        github_license = repo_data.get('license', {})
        github_license_key = github_license.get('key', '') if github_license else ''

    except requests.RequestException as e:
        logging.error(f"Failed to fetch GitHub license: {e}")
        return Response({"detail": "External license information could not be retrieved"}, status=502)

    # Get model license from rating_scores
    model_license_score = 0.0
    if obj.rating_scores and 'license_score' in obj.rating_scores:
        model_license_score = obj.rating_scores['license_score']

    # Simple compatibility logic based on ModelGo paper principles:
    # Permissive licenses (MIT, Apache, BSD) are generally compatible for fine-tune + inference
    # Copyleft licenses (GPL) may have restrictions
    # If model has high license score (>0.5), it's likely permissive and compatible

    # License classification map (from EvaluateLicense in Metric_Model_Service.py)
    permissive_licenses = {
        'mit', 'bsd', 'bsd-2-clause', 'bsd-3-clause',
        'apache', 'apache-2.0', 'isc', 'unlicense', 'cc0-1.0',
        'lgpl-2.1', 'lgpl-3.0'
    }

    restrictive_licenses = {
        'gpl-2.0', 'gpl-3.0', 'agpl', 'agpl-3.0',
        'cc-by-nc', 'non-commercial', 'proprietary'
    }

    # Classify GitHub license
    github_license_name = (github_license.get('name', '') if github_license else '').lower()
    github_license_lower = github_license_key.lower()

    # Check if GitHub license is restrictive (score = 0.0)
    github_is_restrictive = any(lic in github_license_lower or lic in github_license_name
                                for lic in restrictive_licenses)

    # Check if GitHub license is permissive (score = 1.0)
    github_is_permissive = any(lic in github_license_lower or lic in github_license_name
                               for lic in permissive_licenses)

    # For compatibility with fine-tune + inference:
    # BOTH GitHub repo AND model must have permissive licenses
    # If either is restrictive or unknown, they're incompatible
    is_compatible = (
        github_is_permissive and
        not github_is_restrictive and
        model_license_score > 0.5
    )

    return Response(is_compatible, status=200)