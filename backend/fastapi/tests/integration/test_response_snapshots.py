import pytest
import re
from typing import Any, Dict, List, Union

def sanitize_response(data: Any) -> Any:
    """
    Recursively sanitize response data to remove non-deterministic fields.
    Replaces timestamps and volatile fields with placeholders.
    """
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            # Mask timestamps (ISO format or similar strings)
            if k in ["created_at", "updated_at", "timestamp", "last_login", "date", "last_activity"]:
                 new_data[k] = "REDACTED_TIMESTAMP"
            # Mask session IDs or tokens if they look random
            elif k in ["session_id", "access_token", "refresh_token"] and isinstance(v, str):
                new_data[k] = f"REDACTED_{k.upper()}"
            # Mask latency as it varies
            elif k == "latency_ms":
                new_data[k] = 0.0
            # Round floats to prevent precision issues
            elif isinstance(v, float):
                new_data[k] = round(v, 4)
            else:
                new_data[k] = sanitize_response(v)
        return new_data
    elif isinstance(data, list):
        return [sanitize_response(item) for item in data]
    return data

@pytest.mark.snapshot
def test_root_snapshot(client, snapshot):
    """Test the root endpoint response structure."""
    response = client.get("/")
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot

@pytest.mark.snapshot
def test_health_snapshot(client, snapshot):
    """Test the liveness health endpoint response structure."""
    response = client.get("/health")
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot

@pytest.mark.snapshot
def test_v1_health_snapshot(client, snapshot):
    """Test the V1 health endpoint response structure."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot

@pytest.mark.snapshot
def test_v1_questions_snapshot(client, snapshot):
    """Test the questions list response structure."""
    response = client.get("/api/v1/questions", params={"limit": 5})
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot

@pytest.mark.snapshot
def test_v1_categories_snapshot(client, snapshot):
    """Test the categories list response structure."""
    response = client.get("/api/v1/questions/categories")
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot

@pytest.mark.snapshot
def test_v1_assessment_stats_snapshot(client, snapshot):
    """Test the assessment stats response structure."""
    response = client.get("/api/v1/assessments/stats")
    assert response.status_code == 200
    assert sanitize_response(response.json()) == snapshot
