"""
Cache Correctness Verifier - Validates cache consistency, invalidation, TTL, and concurrency.
Issue #1434: Pipeline cache correctness verifier
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a single verification check."""
    check_name: str
    passed: bool
    duration_ms: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = None


@dataclass
class VerificationReport:
    """Overall verification report."""
    timestamp: str
    total_checks: int
    passed: int
    failed: int
    duration_ms: float
    results: List[Dict[str, Any]]


class CacheCorrectnessVerifier:
    """
    Verifies cache correctness across multiple dimensions:
    - Consistency: Same data returns same value
    - Invalidation: Cache invalidation propagates correctly
    - TTL: Entries expire after specified TTL
    - Concurrency: Safe under concurrent access
    """

    def __init__(self, cache_service):
        """
        Args:
            cache_service: CacheService instance to verify
        """
        self.cache_service = cache_service
        self.results: List[VerificationResult] = []
        self.start_time = None

    async def run_all_checks(self) -> VerificationReport:
        """Run all verification checks and return report."""
        self.start_time = time.time()
        self.results = []

        try:
            await self.cache_service.connect()

            # Run all checks
            logger.info("Starting cache correctness verification...")
            await self._check_consistency()
            await self._check_invalidation()
            await self._check_ttl()
            await self._check_concurrency()

            logger.info("Cache correctness verification completed")
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            raise

        return self._generate_report()

    async def _check_consistency(self) -> None:
        """Verify cache returns consistent values for same key."""
        check_name = "consistency"
        start = time.time()
        error = None

        try:
            test_key = "test:consistency:verify"
            test_value = {"data": "test_value", "timestamp": int(time.time())}

            # Set value
            await self.cache_service.set(test_key, test_value, ttl_seconds=60)

            # Read multiple times and verify consistency
            reads = []
            for _ in range(5):
                val = await self.cache_service.get(test_key)
                reads.append(val)

            # Verify all reads are identical
            if not all(v == test_value for v in reads):
                error = "Consistency check failed: values differ across reads"
                self.results.append(
                    VerificationResult(
                        check_name=check_name,
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error_message=error,
                    )
                )
                return

            # Cleanup
            await self.cache_service.delete(test_key)

            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=True,
                    duration_ms=(time.time() - start) * 1000,
                )
            )

        except Exception as e:
            logger.error(f"Consistency check error: {e}")
            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=False,
                    duration_ms=(time.time() - start) * 1000,
                    error_message=str(e),
                )
            )

    async def _check_invalidation(self) -> None:
        """Verify cache invalidation works correctly."""
        check_name = "invalidation"
        start = time.time()
        error = None

        try:
            test_key = "test:invalidation:verify"
            test_value = {"data": "invalidation_test"}

            # Set value
            await self.cache_service.set(test_key, test_value, ttl_seconds=60)

            # Verify it exists
            val_before = await self.cache_service.get(test_key)
            if val_before != test_value:
                error = "Value not set correctly before invalidation"
                raise ValueError(error)

            # Invalidate key
            await self.cache_service.delete(test_key)

            # Verify it's gone
            val_after = await self.cache_service.get(test_key)
            if val_after is not None:
                error = "Invalidation failed: key still exists after delete"
                raise ValueError(error)

            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=True,
                    duration_ms=(time.time() - start) * 1000,
                )
            )

        except Exception as e:
            logger.error(f"Invalidation check error: {e}")
            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=False,
                    duration_ms=(time.time() - start) * 1000,
                    error_message=str(e),
                )
            )

    async def _check_ttl(self) -> None:
        """Verify TTL expiration works correctly."""
        check_name = "ttl"
        start = time.time()
        error = None

        try:
            test_key = "test:ttl:verify"
            test_value = {"data": "ttl_test"}
            ttl_seconds = 2

            # Set with short TTL
            await self.cache_service.set(test_key, test_value, ttl_seconds=ttl_seconds)

            # Verify it exists immediately
            val_immediate = await self.cache_service.get(test_key)
            if val_immediate != test_value:
                error = "Value not retrievable immediately after set"
                raise ValueError(error)

            # Wait for TTL to expire
            await asyncio.sleep(ttl_seconds + 1)

            # Verify it's gone
            val_expired = await self.cache_service.get(test_key)
            if val_expired is not None:
                error = "TTL check failed: value still exists after expiration"
                raise ValueError(error)

            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=True,
                    duration_ms=(time.time() - start) * 1000,
                )
            )

        except Exception as e:
            logger.error(f"TTL check error: {e}")
            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=False,
                    duration_ms=(time.time() - start) * 1000,
                    error_message=str(e),
                )
            )

    async def _check_concurrency(self) -> None:
        """Verify cache is safe under concurrent access."""
        check_name = "concurrency"
        start = time.time()
        error = None

        try:
            test_key = "test:concurrency:verify"
            num_tasks = 10
            reads_per_task = 5

            # Set initial value
            test_value = {"counter": 0, "data": "concurrent_test"}
            await self.cache_service.set(test_key, test_value, ttl_seconds=60)

            # Concurrent reads
            async def concurrent_read(task_id):
                results = []
                for _ in range(reads_per_task):
                    val = await self.cache_service.get(test_key)
                    results.append(val)
                return results

            # Launch concurrent tasks
            tasks = [concurrent_read(i) for i in range(num_tasks)]
            all_results = await asyncio.gather(*tasks)

            # Verify all reads returned consistent value
            for task_results in all_results:
                for val in task_results:
                    if val != test_value:
                        error = "Concurrency check failed: inconsistent values under concurrent read"
                        raise ValueError(error)

            # Cleanup
            await self.cache_service.delete(test_key)

            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=True,
                    duration_ms=(time.time() - start) * 1000,
                    details={"concurrent_tasks": num_tasks, "reads_per_task": reads_per_task},
                )
            )

        except Exception as e:
            logger.error(f"Concurrency check error: {e}")
            self.results.append(
                VerificationResult(
                    check_name=check_name,
                    passed=False,
                    duration_ms=(time.time() - start) * 1000,
                    error_message=str(e),
                )
            )

    def _generate_report(self) -> VerificationReport:
        """Generate verification report from results."""
        duration_ms = (time.time() - self.start_time) * 1000
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        # Convert results to dicts for JSON serialization
        results_dicts = []
        for result in self.results:
            result_dict = {
                "check": result.check_name,
                "passed": result.passed,
                "duration_ms": round(result.duration_ms, 2),
            }
            if result.error_message:
                result_dict["error"] = result.error_message
            if result.details:
                result_dict["details"] = result.details
            results_dicts.append(result_dict)

        report = VerificationReport(
            timestamp=datetime.utcnow().isoformat(),
            total_checks=len(self.results),
            passed=passed,
            failed=failed,
            duration_ms=round(duration_ms, 2),
            results=results_dicts,
        )

        return report


async def run_cache_verification(cache_service) -> Dict[str, Any]:
    """
    Convenience function to run cache verification and return JSON report.
    
    Args:
        cache_service: CacheService instance to verify
        
    Returns:
        Dictionary with verification report
    """
    verifier = CacheCorrectnessVerifier(cache_service)
    report = await verifier.run_all_checks()

    report_dict = {
        "timestamp": report.timestamp,
        "total_checks": report.total_checks,
        "passed": report.passed,
        "failed": report.failed,
        "duration_ms": report.duration_ms,
        "success": report.failed == 0,
        "results": report.results,
    }

    return report_dict
