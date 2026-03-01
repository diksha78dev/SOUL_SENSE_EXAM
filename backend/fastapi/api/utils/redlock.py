import uuid
import logging
from typing import Optional, Tuple
from ..services.cache_service import cache_service
from ....clock_skew_monitor import get_clock_monitor

logger = logging.getLogger("api.utils.redlock")

# Lua: atomically release ONLY if caller holds the exact lock token (TOCTOU-safe)
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua: atomically renew TTL ONLY if caller holds the exact lock token (watchdog/heartbeat)
_RENEW_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class RedlockService:
    """
    Distributed Locking Mechanism using the Redlock algorithm principle in Redis (#1178).
    Prevents Lost Updates by ensuring only one user can edit a resource at a time.

    Enhanced with clock skew resistance (#1195) to prevent TTL inconsistencies
    caused by NTP drift in distributed deployments.
    """

    def __init__(self):
        self._lock_prefix = "lock:team_vision:"
        self._clock_monitor = get_clock_monitor()

    def _key(self, resource_id: str) -> str:
        return f"{self._lock_prefix}{resource_id}"

    async def acquire_lock(
        self, resource_id: str, user_id: int, ttl_seconds: int = 30
    ) -> Tuple[bool, Optional[str]]:
        """
        Acquires a lease on a resource with clock skew resistance.
        Returns (success_boolean, lock_value_or_none).

        Uses monotonic timing with drift tolerance buffers to prevent
        distributed deadlocks from clock skew (#1195).
        """
        await cache_service.connect()
        lock_key = f"{self._lock_prefix}{resource_id}"
        lock_value = f"{user_id}:{uuid.uuid4()}" # Ownership + Unique ID

        # Get clock-skew-resistant TTL with tolerance buffer
        effective_ttl, tolerance = self._clock_monitor.get_time_with_tolerance(ttl_seconds)

        # Log clock skew information for monitoring
        metrics = self._clock_monitor.get_clock_metrics()
        if metrics.state.value != "synchronized":
            logger.warning(f"[Redlock] Clock {metrics.state.value} detected - using {tolerance:.1f}s tolerance buffer")

        # NX: Only set if it doesn't exist
        # EX: Set expiration in seconds (with skew tolerance)
        success = await cache_service.redis.set(
            lock_key,
            lock_value,
            nx=True,
            ex=int(effective_ttl)  # Round to nearest second
        )

        if success:
            logger.info(f"[Redlock] Lock ACQUIRED for resource={resource_id} by user={user_id} (TTL={effective_ttl:.1f}s, tolerance={tolerance:.1f}s)")
            return True, lock_value

        # Check if we already own it (idempotency)
        current_val = await cache_service.redis.get(lock_key)
        if current_val and current_val.startswith(f"{user_id}:"):
            # Already owned, extend it with skew-resistant timing
            await cache_service.redis.expire(lock_key, int(effective_ttl))
            return True, current_val

        logger.warning(f"[Redlock] Lock DENIED for resource={resource_id} - already held by {current_val}")
        return False, None

    async def release_lock(self, resource_id: str, lock_value: str) -> bool:
        """
        Releases the lease ONLY if the presented lock_value matches the stored token.
        Uses a Lua script for atomic compare-and-delete (TOCTOU-safe).
        Returns True on success, False if token mismatch or lock already expired.
        """
        await cache_service.connect()
        result = await cache_service.redis.eval(
            _RELEASE_LUA, 1, self._key(resource_id), lock_value
        )
        if result == 1:
            logger.info(f"[Lock] RELEASED resource={resource_id}")
            return True
        logger.warning(
            f"[Lock] Release FAILED resource={resource_id} — invalid token or expired"
        )
        return False

    async def renew_lock(
        self, resource_id: str, lock_value: str, extend_by_seconds: int = 30
    ) -> bool:
        """
        Watchdog / Heartbeat: Extends the TTL of an active lease if the
        caller presents the correct lock_value token.

        Client contract:
          - Call this endpoint every ~20s when the default TTL is 30s.
          - If this returns False, the lock has expired — re-acquire before continuing.

        Uses a Lua script for atomic compare-then-expire (TOCTOU-safe).
        Returns True on success, False if token mismatch or lock already expired.
        """
        await cache_service.connect()
        result = await cache_service.redis.eval(
            _RENEW_LUA, 1, self._key(resource_id), lock_value, str(extend_by_seconds)
        )
        if result == 1:
            logger.info(f"[Lock] RENEWED resource={resource_id} +{extend_by_seconds}s")
            return True
        logger.warning(
            f"[Lock] Renew FAILED resource={resource_id} — invalid token or expired"
        )
        return False

    async def get_lock_info(self, resource_id: str) -> Optional[dict]:
        """Returns details about who currently holds the lock with clock skew awareness."""
        await cache_service.connect()
        val = await cache_service.redis.get(self._key(resource_id))
        if not val:
            return None

        user_id, _ = val.split(":", 1)
        ttl = await cache_service.redis.ttl(lock_key)

        # Adjust TTL reporting for clock skew
        metrics = self._clock_monitor.get_clock_metrics()
        clock_status = metrics.state.value

        return {
            "user_id": int(user_id),
            "expires_in": ttl,
            "clock_state": clock_status,
            "drift_tolerance": self._clock_monitor.get_drift_tolerance_seconds()
        }


redlock_service = RedlockService()
