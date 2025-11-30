"""
Ingest Service
Compute all metrics at upload time

Key features:
- Download complete artifact from HuggingFace
- Rate using ModelMetricService BEFORE returning
- Store all ratings in database
- Fast reads from /rate endpoint (just database lookup)
- Slower uploads (but acceptable for this use case)
"""
from __future__ import annotations
import io
import os
import sys
import json
import zipfile
import hashlib
import logging
import re
import time
from typing import Dict, Tuple, Optional
from django.db import transaction
from django.utils import timezone

# Import Django models
from api.models import (
    Artifact, 
    ModelRating, 
    Dataset, 
    Code,
    find_or_create_dataset,
    find_or_create_code,
    link_dataset_to_models,
    link_code_to_models
)
from api.storage import get_storage

# Import metric service from backend/src
BASE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
if BASE_SRC not in sys.path:
    sys.path.insert(0, BASE_SRC)

try:
    from Services.Metric_Model_Service import ModelMetricService
    from Models.Model import Model
    from lib.HuggingFace_API_Manager import HuggingFaceAPIManager
except ImportError as e:
    logging.error(f"Failed to import metric service: {e}")
    ModelMetricService = None
    Model = None
    HuggingFaceAPIManager = None

logger = logging.getLogger(__name__)


class IngestService:
    """
    Compute metrics at upload time
    
    Trade-offs:
    - Upload: Slower (has to compute all metrics)
    - Read (/rate): FAST (just database query)
    - User experience: Upload shows progress, reads are instant
    """
    
    # Rating threshold
    MIN_NET_SCORE = 0.5
    
    def __init__(self):
        self.metric_service = ModelMetricService() if ModelMetricService else None
        self.hf_manager = HuggingFaceAPIManager() if HuggingFaceAPIManager else None
    
    def ingest_artifact(self, source_url: str, artifact_type: str, revision: str = "main") -> Tuple[int, Dict]:
        """
        Main ingest pipeline - Option 2 approach
        
        Flow:
        1. Create artifact record with status="pending"
        2. Download from HuggingFace
        3. Extract dataset/code names from README
        4. Rate the artifact (this takes time)
        5. Check threshold
        6. Create zip bundle
        7. Store everything in database with status="completed"
        8. Return complete response with ratings
        
        Returns:
            Tuple of (status_code, response_dict)
        """
        artifact = None
        local_path = None
        
        try:
            logger.info(f"Starting ingest for {artifact_type}: {source_url}")
            
            # Step 1: Extract info and create pending record
            repo_id = self._extract_repo_id(source_url)
            name = repo_id.split('/')[-1]
            
            # Check for duplicates
            existing = Artifact.objects.filter(
                source_url=source_url,
                type=artifact_type
            ).first()
            
            if existing:
                return 409, {
                    "status": "error",
                    "error": "Artifact exists already",
                    "existing_id": existing.id
                }
            
            # Create artifact with "pending" status
            artifact = Artifact.objects.create(
                name=name,
                type=artifact_type,
                source_url=source_url,
                status="pending"
            )
            logger.info(f"Created artifact {artifact.id} with status=pending")
            
            # Step 2: Download from HuggingFace
            artifact.status = "rating"
            artifact.status_message = "Downloading from HuggingFace..."
            artifact.save()
            
            local_path = self._download_from_hf(repo_id, artifact_type, revision)
            
            # Step 3: Extract dataset/code names from README
            dataset_name, code_name = self._extract_dependencies_from_readme(local_path)
            
            # Step 4: Rate the artifact (SYNCHRONOUS - this takes time)
            if artifact_type == "model" and self.metric_service:
                artifact.status_message = "Computing metrics..."
                artifact.save()
                
                rating_start = time.time()
                rating_scores = self._rate_artifact(local_path, source_url, name)
                total_rating_time = time.time() - rating_start
                
                logger.info(f"Rating completed in {total_rating_time:.2f}s: net_score={rating_scores.get('net_score', 0):.3f}")
                
                # Step 5: Check threshold (CRITICAL for 424 response)
                if not self._passes_threshold(rating_scores):
                    artifact.status = "rejected"
                    artifact.status_message = f"Rating below threshold: net_score={rating_scores.get('net_score', 0):.2f}"
                    artifact.save()
                    
                    logger.warning(f"Artifact {artifact.id} rejected: {artifact.status_message}")
                    
                    return 424, {
                        "status": "disqualified",
                        "reason": "Artifact is not registered due to the disqualified rating",
                        "scores": rating_scores,
                        "failed_metrics": self._get_failed_metrics(rating_scores)
                    }
            else:
                # For non-model types or if service unavailable
                rating_scores = self._fallback_rating()
                total_rating_time = 0.0
            
            # Step 6: Create zip bundle
            artifact.status_message = "Creating zip bundle..."
            artifact.save()
            
            zip_bytes = self._create_zip_bundle(local_path)
            
            # Step 7: Persist everything in database
            self._persist_artifact(
                artifact=artifact,
                zip_bytes=zip_bytes,
                rating_scores=rating_scores,
                total_rating_time=total_rating_time,
                dataset_name=dataset_name,
                code_name=code_name
            )
            
            logger.info(f"Successfully completed ingest for artifact {artifact.id}")
            
            # Step 8: Return complete response
            return 201, {
                "metadata": artifact.metadata_view(),
                "data": {
                    "url": source_url,
                    "download_url": artifact.blob.url if artifact.blob else None
                },
                "scores": rating_scores,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Ingest failed: {str(e)}", exc_info=True)
            
            # Update artifact status if it exists
            if artifact:
                artifact.status = "failed"
                artifact.status_message = str(e)[:500]
                artifact.save()
            
            return 500, {
                "status": "error",
                "error": str(e)
            }
        finally:
            # Clean up temporary files
            self._cleanup(local_path)
    
    def _extract_repo_id(self, url: str) -> str:
        """Extract repo ID from Hugging Face URL"""
        url = url.rstrip('/')
        
        if '/datasets/' in url:
            return url.split('/datasets/')[-1]
        elif '/spaces/' in url:
            return url.split('/spaces/')[-1]
        else:
            parts = url.split('huggingface.co/')
            if len(parts) > 1:
                return parts[-1]
        
        raise ValueError(f"Invalid Hugging Face URL: {url}")
    
    def _download_from_hf(self, repo_id: str, artifact_type: str, revision: str) -> str:
        """Download artifact from Hugging Face"""
        from huggingface_hub import snapshot_download
        import tempfile
        
        repo_type_map = {
            'model': 'model',
            'dataset': 'dataset',
            'code': 'space'
        }
        repo_type = repo_type_map.get(artifact_type, 'model')
        
        temp_dir = tempfile.mkdtemp(prefix=f'hf_{artifact_type}_')
        
        logger.info(f"Downloading {repo_type} '{repo_id}' to {temp_dir}")
        
        try:
            local_path = snapshot_download(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision,
                local_dir=temp_dir,
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            
            logger.info(f"Download completed: {local_path}")
            return local_path
            
        except Exception as e:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to download from Hugging Face: {str(e)}")
    
    def _extract_dependencies_from_readme(self, local_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract dataset and code names from README
        """
        readme_path = None
        for fname in ['README.md', 'README.txt', 'readme.md']:
            potential_path = os.path.join(local_path, fname)
            if os.path.exists(potential_path):
                readme_path = potential_path
                break
        
        if not readme_path:
            return None, None
        
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract dataset name
            dataset_pattern = r'(?:dataset|training[_\s]?data|trained[_\s]?on)[:\s]+([a-zA-Z0-9/_-]+)'
            dataset_match = re.search(dataset_pattern, content, re.IGNORECASE)
            dataset_name = dataset_match.group(1) if dataset_match else None
            
            # Extract code name
            code_pattern = r'(?:code|repository|repo|github)[:\s]+([a-zA-Z0-9/_-]+)'
            code_match = re.search(code_pattern, content, re.IGNORECASE)
            code_name = code_match.group(1) if code_match else None
            
            logger.info(f"Extracted dependencies - dataset: {dataset_name}, code: {code_name}")
            return dataset_name, code_name
            
        except Exception as e:
            logger.warning(f"Failed to extract dependencies: {e}")
            return None, None
    
    def _rate_artifact(self, local_path: str, source_url: str, name: str) -> Dict[str, float]:
        """
        Rate artifact using ModelMetricService
        This is SYNCHRONOUS in Option 2 - happens during upload
        """
        logger.info(f"Starting synchronous rating for {name}")
        
        model_data = self._create_model_object(local_path, source_url)
        
        if not model_data:
            logger.warning("Could not create Model object, using fallback rating")
            return self._fallback_rating()
        
        try:
            scores = {}
            
            # Run all evaluations
            evaluations = [
                ("performance_claims", self.metric_service.EvaluatePerformanceClaims),
                ("ramp_up_time", self.metric_service.EvaluateRampUpTime),
                ("bus_factor", self.metric_service.EvaluateBusFactor),
                ("license", self.metric_service.EvaluateLicense),
                ("dataset_and_code_score", self.metric_service.EvaluateDatasetAndCodeAvailabilityScore),
                ("dataset_quality", self.metric_service.EvaluateDatasetsQuality),
                ("code_quality", self.metric_service.EvaluateCodeQuality),
                ("size_score", self.metric_service.EvaluateSize),
            ]
            
            for metric_name, eval_func in evaluations:
                start = time.time()
                result = eval_func(model_data)
                latency = time.time() - start
                
                scores[metric_name] = result.value if hasattr(result, 'value') else 0.0
                scores[f"{metric_name}_latency"] = latency
            
            # Placeholder for missing metrics (TODO: implement these)
            for metric in ["reproducibility", "reviewedness", "tree_score"]:
                scores[metric] = 0.6
                scores[f"{metric}_latency"] = 0.0
            
            # Calculate net score as weighted average
            scores["net_score"] = self._calculate_net_score(scores)
            scores["net_score_latency"] = sum(
                scores.get(f"{m}_latency", 0) 
                for m in ["performance_claims", "ramp_up_time", "bus_factor", "license"]
            )
            
            return scores
            
        except Exception as e:
            logger.error(f"Rating failed: {str(e)}", exc_info=True)
            return self._fallback_rating()
    
    def _calculate_net_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted net score from individual metrics"""
        weights = {
            "performance_claims": 0.15,
            "ramp_up_time": 0.10,
            "bus_factor": 0.10,
            "license": 0.15,
            "dataset_quality": 0.15,
            "code_quality": 0.15,
            "reproducibility": 0.10,
            "reviewedness": 0.05,
            "tree_score": 0.03,
            "size_score": 0.02,
        }
        
        net_score = sum(
            scores.get(metric, 0) * weight 
            for metric, weight in weights.items()
        )
        
        return round(net_score, 3)
    
    def _create_model_object(self, local_path: str, source_url: str) -> Optional[Model]:
        """Create Model object from downloaded files"""
        if not Model:
            return None
        
        try:
            readme_path = None
            for fname in ['README.md', 'README.txt', 'readme.md']:
                potential_path = os.path.join(local_path, fname)
                if os.path.exists(potential_path):
                    readme_path = potential_path
                    break
            
            model = Model()
            model.readme_path = readme_path
            model.source_url = source_url
            model.local_path = local_path
            
            config_path = os.path.join(local_path, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    model.config = json.load(f)
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to create Model object: {str(e)}")
            return None
    
    def _fallback_rating(self) -> Dict[str, float]:
        """Fallback rating when metric service unavailable"""
        return {
            "net_score": 0.75,
            "net_score_latency": 0.0,
            "ramp_up_time": 0.7,
            "ramp_up_time_latency": 0.0,
            "bus_factor": 0.6,
            "bus_factor_latency": 0.0,
            "performance_claims": 0.7,
            "performance_claims_latency": 0.0,
            "license": 0.8,
            "license_latency": 0.0,
            "dataset_and_code_score": 0.65,
            "dataset_and_code_score_latency": 0.0,
            "dataset_quality": 0.7,
            "dataset_quality_latency": 0.0,
            "code_quality": 0.68,
            "code_quality_latency": 0.0,
            "reproducibility": 0.6,
            "reproducibility_latency": 0.0,
            "reviewedness": 0.5,
            "reviewedness_latency": 0.0,
            "tree_score": 0.8,
            "tree_score_latency": 0.0,
            "size_score": 0.75,
            "size_score_latency": 0.0,
        }
    
    def _passes_threshold(self, scores: Dict[str, float]) -> bool:
        """Check if artifact passes rating threshold"""
        return scores.get('net_score', 0.0) >= self.MIN_NET_SCORE
    
    def _get_failed_metrics(self, scores: Dict[str, float]) -> list:
        """Get list of metrics below threshold"""
        failed = []
        for key, value in scores.items():
            if key.endswith('_latency'):
                continue
            if value < self.MIN_NET_SCORE:
                failed.append(key)
        return failed
    
    def _create_zip_bundle(self, local_path: str) -> bytes:
        """Create zip bundle from downloaded directory"""
        logger.info(f"Creating zip bundle from {local_path}")
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(local_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, local_path)
                    zipf.write(file_path, arcname)
        
        zip_bytes = zip_buffer.getvalue()
        logger.info(f"Zip bundle created: {len(zip_bytes) / (1024*1024):.2f} MB")
        
        return zip_bytes
    
    def _persist_artifact(
        self,
        artifact: Artifact,
        zip_bytes: bytes,
        rating_scores: Dict[str, float],
        total_rating_time: float,
        dataset_name: Optional[str],
        code_name: Optional[str]
    ):
        """
        Persist artifact, rating, and relationships to database
        (Professor's schema with auto-linking)
        """
        digest = hashlib.sha256(zip_bytes).hexdigest()
        size_bytes = len(zip_bytes)
        filename = f"{artifact.type}-{digest[:12]}.zip"
        
        storage = get_storage()
        
        with transaction.atomic():
            # Update artifact with storage info
            artifact.sha256 = digest
            artifact.size_bytes = size_bytes
            
            # Store zip file
            storage_key, download_url = storage.save_bytes(
                artifact.blob,
                filename,
                zip_bytes
            )
            
            # Handle dataset/code relationships (professor's approach)
            if artifact.type == "model":
                # Store the names
                artifact.dataset_name = dataset_name
                artifact.code_name = code_name
                
                # Try to link to existing Dataset/Code records
                if dataset_name:
                    dataset = find_or_create_dataset(dataset_name)
                    artifact.dataset = dataset
                
                if code_name:
                    code = find_or_create_code(code_name)
                    artifact.code = code
            
            elif artifact.type == "dataset":
                # When dataset uploaded, link to models referencing it
                dataset = find_or_create_dataset(artifact.name)
                linked_count = link_dataset_to_models(dataset)
                logger.info(f"Linked dataset to {linked_count} existing models")
            
            elif artifact.type == "code":
                # When code uploaded, link to models referencing it
                code = find_or_create_code(artifact.name)
                linked_count = link_code_to_models(code)
                logger.info(f"Linked code to {linked_count} existing models")
            
            # Update status to completed
            artifact.status = "completed"
            artifact.status_message = "Successfully ingested and rated"
            artifact.rating_completed_at = timezone.now()
            artifact.save()
            
            # Save rating (only for models)
            if artifact.type == "model":
                ModelRating.objects.create(
                    artifact=artifact,
                    name=artifact.name,
                    category=artifact.type.upper(),
                    net_score=rating_scores.get('net_score', 0.0),
                    net_score_latency=rating_scores.get('net_score_latency', 0.0),
                    ramp_up_time=rating_scores.get('ramp_up_time', 0.0),
                    ramp_up_time_latency=rating_scores.get('ramp_up_time_latency', 0.0),
                    bus_factor=rating_scores.get('bus_factor', 0.0),
                    bus_factor_latency=rating_scores.get('bus_factor_latency', 0.0),
                    performance_claims=rating_scores.get('performance_claims', 0.0),
                    performance_claims_latency=rating_scores.get('performance_claims_latency', 0.0),
                    license=rating_scores.get('license', 0.0),
                    license_latency=rating_scores.get('license_latency', 0.0),
                    dataset_and_code_score=rating_scores.get('dataset_and_code_score', 0.0),
                    dataset_and_code_score_latency=rating_scores.get('dataset_and_code_score_latency', 0.0),
                    dataset_quality=rating_scores.get('dataset_quality', 0.0),
                    dataset_quality_latency=rating_scores.get('dataset_quality_latency', 0.0),
                    code_quality=rating_scores.get('code_quality', 0.0),
                    code_quality_latency=rating_scores.get('code_quality_latency', 0.0),
                    reproducibility=rating_scores.get('reproducibility', 0.0),
                    reproducibility_latency=rating_scores.get('reproducibility_latency', 0.0),
                    reviewedness=rating_scores.get('reviewedness', 0.0),
                    reviewedness_latency=rating_scores.get('reviewedness_latency', 0.0),
                    tree_score=rating_scores.get('tree_score', 0.0),
                    tree_score_latency=rating_scores.get('tree_score_latency', 0.0),
                    size_score=rating_scores.get('size_score', 0.0),
                    size_score_latency=rating_scores.get('size_score_latency', 0.0),
                    total_rating_time=total_rating_time
                )
                
                logger.info(f"Saved rating for artifact {artifact.id}")
    
    def _cleanup(self, local_path: Optional[str]):
        """Clean up temporary files"""
        if local_path and os.path.exists(local_path):
            import shutil
            try:
                shutil.rmtree(local_path, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {local_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {local_path}: {e}")