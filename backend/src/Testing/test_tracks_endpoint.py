import os
import sys
import pytest
from rest_framework.test import APIClient
from rest_framework import status

# Add backend/web/registry to path so we can import 'registry' and 'api'
# We need to go up 3 levels from backend/src/Testing to backend/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_REGISTRY_DIR = os.path.join(BASE_DIR, "web", "registry")
if WEB_REGISTRY_DIR not in sys.path:
    sys.path.insert(0, WEB_REGISTRY_DIR)

# Set settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "registry.settings")

# Ensure Django is setup
import django
try:
    django.setup()
except Exception:
    pass

@pytest.mark.django_db
class TestTracksEndpoint:
    def test_get_tracks_success(self):
        """Test retrieving the list of planned tracks."""
        client = APIClient()
        response = client.get('/tracks')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "plannedTracks" in data
        assert isinstance(data["plannedTracks"], list)
        # Verify the specific track expected from the view
        assert "Other Security track" in data["plannedTracks"]

    def test_post_tracks_fails(self):
        """Test that POST request to /tracks fails (Method Not Allowed)."""
        client = APIClient()
        response = client.post('/tracks', {})
        
        # Expect 405 Method Not Allowed as per default Django REST framework behavior for @api_view(["GET"])
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
