from rest_framework.test import APITestCase
from rest_framework import status


class HealthAPITests(APITestCase):
    """Test suite for Health API endpoints."""
    
    def test_health_check(self):
        """Test health check endpoint."""
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)
        self.assertIn('timestamp', response.data)
        self.assertIn('database', response.data)

