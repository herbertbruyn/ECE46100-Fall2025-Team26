"""
models.py

Includes:
- All models (Artifact, Dataset, Code, ModelRating) with Access Control
- Access control methods integrated into Artifact
"""
import secrets
import hashlib
from django.db import models
from django.utils import timezone
from datetime import timedelta


# ====================== Access Control Models ======================

class UserGroup(models.Model):
    """User groups for access control"""
    GROUP_TYPES = [
        ('admin', 'Administrator'),
        ('user', 'Regular User'),
    ]
    
    name = models.CharField(max_length=50, choices=GROUP_TYPES, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Permissions
    can_upload = models.BooleanField(default=True)
    can_download = models.BooleanField(default=True)
    can_search = models.BooleanField(default=True)
    can_rate = models.BooleanField(default=True)
    can_delete_any = models.BooleanField(default=False)
    can_reset_registry = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'user_groups'
    
    def __str__(self):
        return self.name


class User(models.Model):
    """User model for authentication"""
    name = models.CharField(max_length=255, unique=True, db_index=True)
    password_hash = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    group = models.ForeignKey(UserGroup, on_delete=models.SET_NULL, null=True, related_name='users')
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'users'
    
    def __str__(self):
        return f"{self.name} ({'admin' if self.is_admin else 'user'})"
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    def check_password(self, password: str) -> bool:
        """Verify password"""
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = timezone.now()
        self.save(update_fields=['last_login'])
    
    def get_permissions(self) -> dict:
        """Get user permissions"""
        if self.is_admin:
            return {
                'can_upload': True,
                'can_download': True,
                'can_search': True,
                'can_rate': True,
                'can_delete_any': True,
                'can_reset_registry': True,
            }
        
        if self.group:
            return {
                'can_upload': self.group.can_upload,
                'can_download': self.group.can_download,
                'can_search': self.group.can_search,
                'can_rate': self.group.can_rate,
                'can_delete_any': self.group.can_delete_any,
                'can_reset_registry': self.group.can_reset_registry,
            }
        
        return {
            'can_upload': True,
            'can_download': True,
            'can_search': True,
            'can_rate': True,
            'can_delete_any': False,
            'can_reset_registry': False,
        }


class AuthToken(models.Model):
    """Authentication tokens"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'auth_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"Token for {self.user.name}"
    
    @classmethod
    def generate_token(cls, user, expires_in_hours: int = 24) -> str:
        """Generate a new token"""
        raw_token = secrets.token_urlsafe(32)
        token_string = f"bearer {raw_token}"
        expires_at = timezone.now() + timedelta(hours=expires_in_hours)
        
        cls.objects.create(
            user=user,
            token=token_string,
            expires_at=expires_at
        )
        
        return token_string
    
    def is_valid(self) -> bool:
        """Check if token is valid"""
        return self.user.is_active and timezone.now() <= self.expires_at
    
    def update_last_used(self):
        """Update last used timestamp"""
        self.last_used = timezone.now()
        self.save(update_fields=['last_used'])
    
    @classmethod
    def cleanup_expired(cls):
        """Delete expired tokens"""
        expired = cls.objects.filter(expires_at__lt=timezone.now())
        count = expired.count()
        expired.delete()
        return count


# ====================== Existing Models ======================

class Dataset(models.Model):
    """Separate table for datasets"""
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'datasets'
    
    def __str__(self):
        return self.name


class Code(models.Model):
    """Separate table for code repositories"""
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'code_repos'
    
    def __str__(self):
        return self.name


class Artifact(models.Model):
    """Main artifact table with access control"""
    ARTIFACT_TYPES = [
        ("model", "Model"),
        ("dataset", "Dataset"),
        ("code", "Code")
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("downloading", "Downloading"),
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

    # Foreign keys
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
    
    # Access control
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_artifacts'
    )
    is_public = models.BooleanField(default=True)

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
    
    # Access control methods
    def can_user_access(self, user) -> bool:
        """Check if user can access this artifact"""
        if not user:
            return self.is_public
        
        if user.is_admin:
            return True
        
        if self.is_public:
            return True
        
        if self.uploaded_by == user:
            return True
        
        return self.permissions.filter(user=user).exists()
    
    def can_user_modify(self, user) -> bool:
        """Check if user can modify this artifact"""
        if not user:
            return False
        
        if user.is_admin:
            return True
        
        if self.uploaded_by == user:
            return True
        
        return self.permissions.filter(
            user=user,
            permission_type__in=['owner', 'editor']
        ).exists()
    
    def can_user_delete(self, user) -> bool:
        """Check if user can delete this artifact"""
        if not user:
            return False
        
        if user.is_admin:
            return True
        
        if self.uploaded_by == user:
            return True
        
        return self.permissions.filter(
            user=user,
            permission_type='owner'
        ).exists()
    
    def __str__(self):
        return f"{self.type}/{self.name} ({self.id})"


class ArtifactPermission(models.Model):
    """Per-artifact permissions (optional)"""
    PERMISSION_TYPES = [
        ('owner', 'Owner'),
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]
    
    artifact = models.ForeignKey(
        Artifact,
        on_delete=models.CASCADE,
        related_name='permissions'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='artifact_permissions'
    )
    permission_type = models.CharField(max_length=20, choices=PERMISSION_TYPES)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='granted_permissions'
    )
    
    class Meta:
        db_table = 'artifact_permissions'
        unique_together = [('artifact', 'user')]
    
    def __str__(self):
        return f"{self.user.name} - {self.permission_type} - {self.artifact.name}"


class ModelInfo(models.Model):
    """Legacy model info"""
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
    """Rating metrics for model artifacts"""
    artifact = models.OneToOneField(
        Artifact,
        on_delete=models.CASCADE,
        related_name="rating",
        primary_key=True
    )
    
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    
    # All metrics
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    total_rating_time = models.FloatField()
    
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