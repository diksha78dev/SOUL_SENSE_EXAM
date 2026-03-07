"""
Integration tests for cache correctness verifier.
Tests basic functionality, requires unit tests for mocked testing.

Note: Full integration testing with Redis requires Redis running.
Unit tests (test_cache_correctness_verifier.py) provide comprehensive
coverage with mocked cache service.
"""

import pytest
from backend.fastapi.api.services.cache_correctness_verifier import (
    CacheCorrectnessVerifier,
    VerificationResult,
    VerificationReport,
    run_cache_verification,
)

pytestmark = pytest.mark.integration


def test_verification_result_dataclass():
    """Test VerificationResult dataclass."""
    result = VerificationResult(
        check_name="consistency",
        passed=True,
        duration_ms=15.5,
        error_message=None,
        details=None
    )
    
    assert result.check_name == "consistency"
    assert result.passed is True
    assert result.duration_ms == 15.5


def test_verification_report_dataclass():
    """Test VerificationReport dataclass."""
    results = [
        {"check": "consistency", "passed": True, "duration_ms": 20.0},
        {"check": "invalidation", "passed": True, "duration_ms": 15.0},
    ]
    
    report = VerificationReport(
        timestamp="2026-03-07T12:00:00.000000",
        total_checks=2,
        passed=2,
        failed=0,
        duration_ms=35.0,
        results=results
    )
    
    assert report.total_checks == 2
    assert report.passed == 2
    assert report.failed == 0
    assert len(report.results) == 2


@pytest.mark.asyncio
async def test_verifier_instantiation():
    """Test that verifier can be instantiated."""
    from unittest.mock import AsyncMock
    
    mock_cache = AsyncMock()
    verifier = CacheCorrectnessVerifier(mock_cache)
    
    assert verifier is not None
    assert verifier.cache_service is mock_cache
    assert verifier.results == []
    assert verifier.start_time is None


@pytest.mark.asyncio
async def test_verification_report_generation():
    """Test report generation with mock data."""
    from unittest.mock import AsyncMock
    
    mock_cache = AsyncMock()
    mock_cache.connect = AsyncMock()
    
    # Setup minimal mock
    stored_value = {}
    
    async def mock_set(key, value, ttl_seconds=None):
        stored_value[key] = value
        return None
    
    async def mock_get(key):
        return stored_value.get(key)
    
    async def mock_delete(key):
        stored_value.pop(key, None)
        return None
    
    mock_cache.set.side_effect = mock_set
    mock_cache.get.side_effect = mock_get
    mock_cache.delete.side_effect = mock_delete
    
    verifier = CacheCorrectnessVerifier(mock_cache)
    report = await verifier.run_all_checks()
    
    # Verify report structure
    assert report.timestamp is not None
    assert report.total_checks == 4
    assert report.duration_ms >= 0
    assert len(report.results) == 4
    
    # Verify results structure
    for result in report.results:
        assert "check" in result
        assert "passed" in result
        assert "duration_ms" in result


def test_cache_service_imports():
    """Test that cache service can be imported."""
    from backend.fastapi.api.services.cache_service import CacheService
    
    service = CacheService()
    assert service is not None


@pytest.mark.asyncio
async def test_manual_verification_results():
    """Test manual creation of verification results."""
    result1 = VerificationResult(
        check_name="consistency",
        passed=True,
        duration_ms=10.5,
    )
    
    result2 = VerificationResult(
        check_name="invalidation",
        passed=False,
        duration_ms=5.0,
        error_message="Cache key still exists after delete"
    )
    
    assert result1.passed is True
    assert result2.passed is False
    assert "Cache key" in result2.error_message
