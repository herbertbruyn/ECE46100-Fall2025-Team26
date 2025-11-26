"""
models.py with Dataset, Code, and ModelRating
"""
from django.db import models
from django.db.models import Q


class Dataset(models.Model):
    """
    Separate table for datasets (professor's recommendation)
    """
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'datasets'
    
    def __str__(self):
        return self.name


class Code(models.Model):
    """
    Separate table for code repositories
    """
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'code_repos'
    
    def __str__(self):
        return self.name


class Artifact(models.Model):
    """
    Main artifact table - supports models, datasets, and code
    """
    ARTIFACT_TYPES = [
        ("model", "Model"),
        ("dataset", "Dataset"),
        ("code", "Code")
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("rating", "Rating"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("rejected", "Rejected"),
    ]

    # Core fields
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, db_index=True)
    type = models.CharField(max_length=16, choices=ARTIFACT_TYPES, db_index=True)
    source_url = models.URLField()
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True
    )
    status_message = models.TextField(blank=True, null=True)
    
    # Storage
    blob = models.FileField(upload_to="registry/raw/", blank=True)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    size_bytes = models.BigIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rating_completed_at = models.DateTimeField(blank=True, null=True)

    # Foreign keys (professor's schema)
    dataset_name = models.CharField(max_length=256, blank=True, null=True)
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="models_using_this"
    )
    
    code_name = models.CharField(max_length=256, blank=True, null=True)
    code = models.ForeignKey(
        Code,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="models_using_this"
    )

    class Meta:
        db_table = 'artifacts'
        indexes = [
            models.Index(fields=['name', 'type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_url', 'type'],
                name='unique_source_per_type'
            )
        ]

    def metadata_view(self) -> dict:
        """API response format"""
        return {
            "name": self.name,
            "id": self.id,
            "type": self.type
        }

    def to_artifact_view(self) -> dict:
        """Complete artifact view"""
        return {
            "metadata": self.metadata_view(),
            "data": {
                "url": self.source_url,
                "download_url": self.blob.url if self.blob else None
            }
        }
    
    def __str__(self):
        return f"{self.type}/{self.name} ({self.id})"


class ModelInfo(models.Model):
    """Legacy model info (can be removed if not used)"""
    artifact = models.OneToOneField(
        Artifact,
        on_delete=models.CASCADE,
        related_name="modelinfo"
    )
    dataset_name = models.CharField(max_length=256, null=True, blank=True)
    dataset = models.ForeignKey(
        Artifact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="models_using_dataset"
    )
    code_name = models.CharField(max_length=256, null=True, blank=True)
    code = models.ForeignKey(
        Artifact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="models_using_code"
    )


class ModelRating(models.Model):
    """
    Rating metrics for model artifacts
    """
    artifact = models.OneToOneField(
        Artifact,
        on_delete=models.CASCADE,
        related_name="rating",
        primary_key=True
    )
    
    # Basic info
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    
    # All required metrics with latencies
    net_score = models.FloatField()
    net_score_latency = models.FloatField()
    
    ramp_up_time = models.FloatField()
    ramp_up_time_latency = models.FloatField()
    
    bus_factor = models.FloatField()
    bus_factor_latency = models.FloatField()
    
    performance_claims = models.FloatField()
    performance_claims_latency = models.FloatField()
    
    license = models.FloatField()
    license_latency = models.FloatField()
    
    dataset_and_code_score = models.FloatField()
    dataset_and_code_score_latency = models.FloatField()
    
    dataset_quality = models.FloatField()
    dataset_quality_latency = models.FloatField()
    
    code_quality = models.FloatField()
    code_quality_latency = models.FloatField()
    
    reproducibility = models.FloatField()
    reproducibility_latency = models.FloatField()
    
    reviewedness = models.FloatField()
    reviewedness_latency = models.FloatField()
    
    tree_score = models.FloatField()
    tree_score_latency = models.FloatField()
    
    size_score = models.FloatField()
    size_score_latency = models.FloatField()
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    total_rating_time = models.FloatField(
        help_text="Total time to compute all metrics (seconds)"
    )
    
    class Meta:
        db_table = 'model_ratings'
    
    def to_dict(self) -> dict:
        """Convert to API response format"""
        return {
            "name": self.name,
            "category": self.category,
            "net_score": self.net_score,
            "net_score_latency": self.net_score_latency,
            "ramp_up_time": self.ramp_up_time,
            "ramp_up_time_latency": self.ramp_up_time_latency,
            "bus_factor": self.bus_factor,
            "bus_factor_latency": self.bus_factor_latency,
            "performance_claims": self.performance_claims,
            "performance_claims_latency": self.performance_claims_latency,
            "license": self.license,
            "license_latency": self.license_latency,
            "dataset_and_code_score": self.dataset_and_code_score,
            "dataset_and_code_score_latency": self.dataset_and_code_score_latency,
            "dataset_quality": self.dataset_quality,
            "dataset_quality_latency": self.dataset_quality_latency,
            "code_quality": self.code_quality,
            "code_quality_latency": self.code_quality_latency,
            "reproducibility": self.reproducibility,
            "reproducibility_latency": self.reproducibility_latency,
            "reviewedness": self.reviewedness,
            "reviewedness_latency": self.reviewedness_latency,
            "tree_score": self.tree_score,
            "tree_score_latency": self.tree_score_latency,
            "size_score": self.size_score,
            "size_score_latency": self.size_score_latency,
        }
    
    def __str__(self):
        return f"Rating for {self.artifact.name}: {self.net_score:.2f}"


# Helper functions
def find_or_create_dataset(dataset_name: str) -> Dataset:
    """Find or create dataset by name"""
    if not dataset_name:
        return None
    dataset, created = Dataset.objects.get_or_create(name=dataset_name.strip())
    return dataset


def find_or_create_code(code_name: str) -> Code:
    """Find or create code repo by name"""
    if not code_name:
        return None
    code, created = Code.objects.get_or_create(name=code_name.strip())
    return code


def link_dataset_to_models(dataset: Dataset):
    """Link dataset to models referencing it"""
    models_to_update = Artifact.objects.filter(
        type="model",
        dataset_name__iexact=dataset.name,
        dataset__isnull=True
    )
    updated = models_to_update.update(dataset=dataset)
    return updated


def link_code_to_models(code: Code):
    """Link code to models referencing it"""
    models_to_update = Artifact.objects.filter(
        type="model",
        code_name__iexact=code.name,
        code__isnull=True
    )
    updated = models_to_update.update(code=code)
    return updated