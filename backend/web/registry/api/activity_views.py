"""
api/activity_views.py

Activity Log Views

Implements:
- GET /activity - Get activity logs with filters
"""
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q

from .models import ActivityLog
from .serializers import ActivityLogSerializer
from .auth import optional_auth

logger = logging.getLogger(__name__)


@api_view(["GET"])
@optional_auth
def get_activity_logs(request):
    """
    GET /activity

    Get activity logs with optional filters.

    Query parameters:
    - user: Filter by username
    - action: Filter by action type (upload, delete, download, etc.)
    - artifact_type: Filter by artifact type (model, dataset, code)
    - date_from: Filter by start date (ISO format)
    - date_to: Filter by end date (ISO format)
    - limit: Number of results to return (default: 100, max: 1000)
    - offset: Pagination offset (default: 0)

    Returns:
        200: Array of activity log entries
    """
    try:
        # Start with all logs
        queryset = ActivityLog.objects.all()

        # Apply filters from query parameters
        user_filter = request.GET.get('user')
        if user_filter:
            queryset = queryset.filter(user__icontains=user_filter)

        action_filter = request.GET.get('action')
        if action_filter:
            queryset = queryset.filter(action=action_filter)

        artifact_type_filter = request.GET.get('artifact_type')
        if artifact_type_filter:
            queryset = queryset.filter(artifact_type=artifact_type_filter)

        date_from = request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)

        date_to = request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)

        # Pagination
        try:
            limit = min(int(request.GET.get('limit', 100)), 1000)
        except ValueError:
            limit = 100

        try:
            offset = int(request.GET.get('offset', 0))
        except ValueError:
            offset = 0

        # Get total count before pagination
        total_count = queryset.count()

        # Apply pagination
        queryset = queryset[offset:offset + limit]

        # Serialize
        serializer = ActivityLogSerializer(queryset, many=True)

        logger.info(f"Retrieved {len(serializer.data)} activity logs (total: {total_count})")

        return Response({
            'results': serializer.data,
            'count': len(serializer.data),
            'total': total_count,
            'offset': offset,
            'limit': limit
        }, status=200)

    except Exception as e:
        logger.error(f"Error retrieving activity logs: {str(e)}", exc_info=True)
        return Response(
            {"detail": f"Failed to retrieve activity logs: {str(e)}"},
            status=500
        )


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
