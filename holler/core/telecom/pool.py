"""DID number pool management.

Implements atomic checkout and release of DIDs (Direct Inward Dialing numbers)
using Redis SET operations. SPOP is genuinely atomic — no additional locking
is needed for single-member pop on a SET.

Per D-01: DID pool stored in Redis SET.
Per D-02: Pool initialized from config-defined list of DIDs.
Per D-03: No call can originate without a checked-out DID.

Design note: Using redis.asyncio (redis-py 7.x) which is already in
pyproject.toml dependencies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class NumberPoolExhaustedError(Exception):
    """Raised when checkout() is attempted on an empty number pool.

    Per D-03: if the pool is empty, the call fails with a clear error.
    """


class NumberPool:
    """Atomic DID checkout and release via Redis SET.

    One Redis SET holds all available DIDs. SPOP atomically removes one
    member (checkout); SADD atomically adds it back (release). Since SET
    members are unique, SADD is naturally idempotent — adding the same DID
    twice results in one entry.

    Usage:
        import redis.asyncio as aioredis
        client = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
        pool = NumberPool(client)
        await pool.initialize(["+15550001234", "+15550005678"])

        did = await pool.checkout()   # Atomically removes from pool
        try:
            # ... make call with did ...
        finally:
            await pool.release(did)   # Returns to pool
    """

    def __init__(
        self,
        redis_client,
        pool_key: str = "holler:did_pool",
    ) -> None:
        """Initialize the NumberPool.

        Args:
            redis_client: Async Redis client (redis.asyncio.Redis). Must be
                          created with decode_responses=True to return strings.
            pool_key: Redis SET key name for the DID pool.
        """
        self._redis = redis_client
        self._pool_key = pool_key

    async def checkout(self) -> str:
        """Atomically check out a DID from the pool.

        Uses Redis SPOP to atomically remove and return one random member
        from the SET. This is race-condition-free for concurrent callers.

        Returns:
            An E.164 DID string (e.g. "+15550001234").

        Raises:
            NumberPoolExhaustedError: If the pool is empty (no DIDs available).
        """
        did = await self._redis.spop(self._pool_key)
        if did is None:
            raise NumberPoolExhaustedError(
                f"Number pool '{self._pool_key}' is exhausted — no DIDs available. "
                "Add DIDs to the pool via pool.initialize() or HOLLER_POOL_DIDS config."
            )
        # Defensive: handle bytes-vs-str edge case (in case decode_responses
        # is not set on the client)
        if isinstance(did, bytes):
            did = did.decode()
        return did

    async def release(self, did: str) -> None:
        """Return a DID back to the pool after a call ends.

        Uses Redis SADD to add the DID back. SADD is idempotent — adding a
        DID that already exists in the SET is a no-op (no duplicates).

        Args:
            did: E.164 DID string to return to the pool.
        """
        await self._redis.sadd(self._pool_key, did)

    async def initialize(self, dids: List[str]) -> None:
        """Populate the pool with a list of DIDs.

        Uses Redis SADD which is idempotent — calling initialize() multiple
        times with the same DIDs will not create duplicates because SET
        members are unique.

        Args:
            dids: List of E.164 DID strings to add to the pool.
        """
        if not dids:
            return
        await self._redis.sadd(self._pool_key, *dids)

    async def available(self) -> int:
        """Return the number of DIDs currently available in the pool.

        Uses Redis SCARD (set cardinality).

        Returns:
            Integer count of available DIDs.
        """
        return await self._redis.scard(self._pool_key)
