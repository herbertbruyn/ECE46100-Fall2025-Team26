from rest_framework import serializers

class ArtifactCreateSerializer(serializers.Serializer):
    url = serializers.URLField()     # body must be {"url":"https://..."}

class ArtifactRegexSerializer(serializers.Serializer):
    regex = serializers.CharField()  # body must be {"regex":"..."}
