from rest_framework import serializers
from .models import ActivityLog

class ArtifactCreateSerializer(serializers.Serializer):
    url = serializers.URLField()     # body must be {"url":"https://..."}

class ArtifactRegexSerializer(serializers.Serializer):
    regex = serializers.CharField()  # body must be {"regex":"..."}

class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'action', 'artifact_type', 'artifact_id', 'artifact_name', 'details', 'ip_address', 'timestamp']
        read_only_fields = fields
