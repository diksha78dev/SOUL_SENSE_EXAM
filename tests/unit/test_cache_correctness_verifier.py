"""
Unit tests for cache correctness verifier.
Tests with mocked cache service.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.fastapi.api.services.cache_correctness_verifier import (
    CacheCorrectnessVerifier,
    run_cache_verification,
)


@pytest.fixture
def mock_cache_service():
    """Create a mock cache service."""
    service = AsyncMock()
    service.connect = AsyncMock()
    service.get = AsyncMock()
    service.set = AsyncMock()
    service.delete = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_consistency_check_passes(mock_cache_service):
    """Test consistency check passes when values are consistent."""
    # Use a callable to capture the set value and return it on get
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value['value'] = value
        return None
    
    async def mock_get(key):
        # Return the stored value (or a copy to ensure consistency)
        return stored_value.get('value')
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_consistency()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is True
    assert verifier.results[0].check_name == "consistency"


@pytest.mark.asyncio
async def test_consistency_check_fails_on_inconsistent_values(mock_cache_service):
    """Test consistency check fails when values differ."""
    # Alternate between two different stored values to simulate inconsistency
    values = [{"data": "value1"}, {"data": "value2"}]
    call_count = {}
    
    async def mock_get(key):
        call_count['count'] = call_count.get('count', 0) + 1
        # Alternate between values to simulate inconsistency
        return values[call_count['count'] % 2]
    
    mock_cache_service.set.return_value = None
    mock_cache_service.get.side_effect = mock_get

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_consistency()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is False
    assert "Consistency check failed" in verifier.results[0].error_message


@pytest.mark.asyncio
async def test_invalidation_check_passes(mock_cache_service):
    """Test invalidation check passes when key is deleted."""
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value['value'] = value
        return None
    
    async def mock_get(key):
        return stored_value.get('value')
    
    async def mock_delete(key):
        stored_value.pop('value', None)
        return None
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_invalidation()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is True
    assert verifier.results[0].check_name == "invalidation"


@pytest.mark.asyncio
async def test_invalidation_check_fails_when_key_not_deleted(mock_cache_service):
    """Test invalidation check fails when key is not deleted."""
    # Key persists even after delete attempt
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        return stored_value.get(key)
    
    async def mock_delete(key):
        # Delete doesn't actually remove (simulating failure)
        return None
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_invalidation()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is False
    assert "Invalidation failed" in verifier.results[0].error_message


@pytest.mark.asyncio
async def test_ttl_check_passes(mock_cache_service):
    """Test TTL check passes when value expires."""
    stored_value = {}
    calls = {"count": 0}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        calls["count"] += 1
        if calls["count"] == 1:
            # First call: value exists
            return stored_value.get(key)
        else:
            # After sleep: value is gone (TTL expired)
            return None
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_ttl()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is True
    assert verifier.results[0].check_name == "ttl"


@pytest.mark.asyncio
async def test_ttl_check_fails_when_value_not_expired(mock_cache_service):
    """Test TTL check fails when value doesn't expire."""
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        # Always return the value (never expires)
        return stored_value.get(key)
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_ttl()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is False
    assert "TTL check failed" in verifier.results[0].error_message


@pytest.mark.asyncio
async def test_concurrency_check_passes(mock_cache_service):
    """Test concurrency check passes with consistent concurrent access."""
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value['value'] = value
        return None
    
    async def mock_get(key):
        return stored_value.get('value')
    
    async def mock_delete(key):
        stored_value.pop('value', None)
        return None
    
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_concurrency()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is True
    assert verifier.results[0].check_name == "concurrency"


@pytest.mark.asyncio
async def test_concurrency_check_fails_on_inconsistent_reads(mock_cache_service):
    """Test concurrency check fails when concurrent reads are inconsistent."""
    # Alternate between two values to simulate race condition
    values = [{"data": "value1"}, {"data": "value2"}]
    call_count = {}
    
    async def mock_get(key):
        call_count['count'] = call_count.get('count', 0) + 1
        return values[call_count['count'] % 2]
    
    mock_cache_service.set.return_value = None
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.return_value = None

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_concurrency()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is False
    assert "Concurrency check failed" in verifier.results[0].error_message


@pytest.mark.asyncio
async def test_run_all_checks(mock_cache_service):
    """Test running all checks generates complete report."""
    # Simple mock setup for running all checks
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        return stored_value.get(key)
    
    async def mock_delete(key):
        stored_value.pop(key, None)
        return None
    
    mock_cache_service.connect = AsyncMock()
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    report = await verifier.run_all_checks()

    assert report.total_checks == 4
    # At least some checks should pass with basic mock
    assert report.total_checks > 0
    assert len(report.results) == 4

    # Verify report structure
    check_names = [r["check"] for r in report.results]
    assert "consistency" in check_names
    assert "invalidation" in check_names
    assert "ttl" in check_names
    assert "concurrency" in check_names


@pytest.mark.asyncio
async def test_run_cache_verification_function(mock_cache_service):
    """Test convenience function run_cache_verification."""
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        return stored_value.get(key)
    
    async def mock_delete(key):
        stored_value.pop(key, None)
        return None
    
    mock_cache_service.connect = AsyncMock()
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    report = await run_cache_verification(mock_cache_service)

    # Verify report structure
    assert "success" in report
    assert "total_checks" in report
    assert "passed" in report
    assert "failed" in report
    assert report["total_checks"] == 4
    assert "timestamp" in report
    assert "duration_ms" in report


@pytest.mark.asyncio
async def test_verification_handles_exception(mock_cache_service):
    """Test verification gracefully handles exceptions."""
    mock_cache_service.connect.side_effect = RuntimeError("Connection failed")

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    
    with pytest.raises(RuntimeError):
        await verifier.run_all_checks()


@pytest.mark.asyncio
async def test_individual_check_exception_handling(mock_cache_service):
    """Test individual checks handle exceptions."""
    mock_cache_service.set.side_effect = RuntimeError("Set failed")

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    await verifier._check_consistency()

    assert len(verifier.results) == 1
    assert verifier.results[0].passed is False
    assert "Set failed" in verifier.results[0].error_message


@pytest.mark.asyncio
async def test_report_includes_check_duration(mock_cache_service):
    """Test report includes duration metrics."""
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        return stored_value.get(key)
    
    async def mock_delete(key):
        stored_value.pop(key, None)
        return None
    
    mock_cache_service.connect = AsyncMock()
    mock_cache_service.set.side_effect = mock_set
    mock_cache_service.get.side_effect = mock_get
    mock_cache_service.delete.side_effect = mock_delete

    verifier = CacheCorrectnessVerifier(mock_cache_service)
    report = await verifier.run_all_checks()

    for result in report.results:
        assert result["duration_ms"] >= 0
    assert report.duration_ms > 0
