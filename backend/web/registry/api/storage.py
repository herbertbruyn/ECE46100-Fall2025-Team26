from __future__ import annotations
import boto3
from django.conf import settings
from django.core.files.base import ContentFile
from typing import Tuple

class LocalStorage:
    def save_bytes(self, django_file_field, filename: str, data: bytes) -> tuple[str, str]:
        django_file_field.save(filename, ContentFile(data))  # MEDIA_ROOT/...
        key = django_file_field.name                         # "registry/raw/<file>"
        url = django_file_field.url                          # "/media/registry/raw/<file>"
        return key, url

class S3Storage:
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        
        self.bucket = settings.AWS_STORAGE_BUCKET_NAME
        if not self.bucket:
            raise ValueError("AWS_STORAGE_BUCKET_NAME is required when USE_S3=True")
        
        self.s3 = boto3.client(
            "s3", 
            region_name=settings.AWS_S3_REGION_NAME,
            config=boto3.session.Config(connect_timeout=10, read_timeout=30)
        )
        logger.info(f"S3Storage initialized for bucket: {self.bucket}")

    def save_bytes(self, django_file_field, filename: str, data: bytes) -> tuple[str, str]:
        import logging
        logger = logging.getLogger(__name__)
        
        key = f"registry/raw/{filename}"
        logger.info(f"Uploading {len(data)} bytes to s3://{self.bucket}/{key}")
        
        try:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
            logger.info(f"Successfully uploaded to S3: {key}")
        except Exception as e:
            logger.error(f"S3 upload failed: {e}", exc_info=True)
            raise
        
        django_file_field.name = key
        url = self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=600
        )
        return key, url

def get_storage():
    return S3Storage() if getattr(settings, "USE_S3", False) else LocalStorage()