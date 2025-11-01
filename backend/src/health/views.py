from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from django.db import connection
from django.utils import timezone
import sys


class HealthCheckView(APIView):
    """
    GET /api/health/ - System health check endpoint
    """
    
    @extend_schema(
        description="Check system health and status",
        responses={200: dict}
    )
    def get(self, request):
        """
        Return system health information including:
        - Database connectivity
        - Python version
        - Django status
        - Timestamp
        """
        health_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'python_version': sys.version,
            'database': self._check_database(),
            'services': {
                'api': 'operational',
                'metrics': 'operational',
                'packages': 'operational',
            }
        }
        
        return Response(health_data, status=status.HTTP_200_OK)
    
    def _check_database(self):
        """Check database connectivity."""
        try:
            connection.ensure_connection()
            return {
                'status': 'connected',
                'vendor': connection.vendor
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

