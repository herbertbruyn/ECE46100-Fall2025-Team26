"""
Services package for artifact ingestion and processing
"""
from .ingest import IngestService

# Import S3 optimized service if available
try:
    from .ingest_s3_optimized import S3OptimizedIngestService
    __all__ = ['IngestService', 'S3OptimizedIngestService']
except ImportError:
    __all__ = ['IngestService']
