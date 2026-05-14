import pytest
from fastapi import status


class TestMain:
    def test_root_endpoint(self, test_client):
        response = test_client.get("/api/projects")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []
    
    def test_health_check(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == {"status": "ok"}
    
    @pytest.mark.slow
    def test_performance_endpoint(self, test_client):
        response = test_client.get("/api/auth/me")
        assert response.status_code == status.HTTP_403_FORBIDDEN
