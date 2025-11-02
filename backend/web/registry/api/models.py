from django.db import models

class Artifact(models.Model):
    # we support exactly these 3 types for the MVP
    ARTIFACT_TYPES = [("model", "Model"), ("dataset", "Dataset"), ("code", "Code")]

    id = models.BigAutoField(primary_key=True)   # numeric id matches typical examples
    name = models.CharField(max_length=255, db_index=True)  # search by regex
    type = models.CharField(max_length=16, choices=ARTIFACT_TYPES)
    source_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("name", "type", "source_url")]
        # This gives us a predictable 409 on duplicate create

    # Helpers to shape responses exactly like your OpenAPI
    def metadata_view(self) -> dict:
        return {"name": self.name, "id": self.id, "type": self.type}

    def to_artifact_view(self) -> dict:
        return {"metadata": self.metadata_view(), "data": {"url": self.source_url}}
