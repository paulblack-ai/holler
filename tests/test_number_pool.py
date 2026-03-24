"""Tests for NumberPool with Redis SPOP/SADD.

Uses a real redis.asyncio.Redis client at localhost:6379.
Tests are skipped if Redis is not available.
"""
import asyncio
import pytest

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = False
    try:
        # Quick connectivity check
        def _check_redis():
            client = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(client.ping())
                return True
            except Exception:
                return False
            finally:
                loop.run_until_complete(client.aclose())
                loop.close()
        _REDIS_AVAILABLE = _check_redis()
    except Exception:
        _REDIS_AVAILABLE = False
except ImportError:
    _REDIS_AVAILABLE = False

REDIS_SKIP = pytest.mark.skipif(
    not _REDIS_AVAILABLE,
    reason="Redis not available at localhost:6379"
)

from holler.core.telecom.pool import NumberPool, NumberPoolExhaustedError

# Use a test-specific key to avoid colliding with production pool
TEST_POOL_KEY = "holler:did_pool:test"


def get_redis():
    """Create a Redis client for testing."""
    return aioredis.Redis(host="localhost", port=6379, decode_responses=True)


def run(coro):
    """Run a coroutine synchronously using a dedicated event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def cleanup(redis_client):
    """Remove the test pool key."""
    await redis_client.delete(TEST_POOL_KEY)


@REDIS_SKIP
def test_checkout_returns_did():
    """checkout() returns a DID string when the pool has members."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            await pool.initialize(["+15550001111"])
            did = await pool.checkout()
            assert did == "+15550001111"
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())


@REDIS_SKIP
def test_checkout_raises_when_empty():
    """checkout() raises NumberPoolExhaustedError when the pool is empty."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            await cleanup(client)  # Ensure pool is empty
            with pytest.raises(NumberPoolExhaustedError):
                await pool.checkout()
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())


@REDIS_SKIP
def test_release_returns_did_to_pool():
    """release() adds a DID back to the pool (can be checked out again)."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            await pool.initialize(["+15550002222"])
            did = await pool.checkout()
            assert did == "+15550002222"

            # Pool should be empty now
            assert await pool.available() == 0

            # Release back
            await pool.release(did)
            assert await pool.available() == 1

            # Can check out again
            did2 = await pool.checkout()
            assert did2 == "+15550002222"
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())


@REDIS_SKIP
def test_initialize_populates_pool():
    """initialize() populates pool from a list of DIDs."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            await cleanup(client)  # Start empty
            await pool.initialize(["+15550003333", "+15550004444", "+15550005555"])
            count = await pool.available()
            assert count == 3
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())


@REDIS_SKIP
def test_initialize_is_idempotent():
    """initialize() is idempotent — adding same DIDs twice doesn't duplicate."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            dids = ["+15550006666", "+15550007777"]
            await pool.initialize(dids)
            await pool.initialize(dids)  # Second call — should not duplicate
            count = await pool.available()
            assert count == 2
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())


@REDIS_SKIP
def test_available_returns_count():
    """available() returns the count of DIDs in the pool."""
    async def _test():
        client = get_redis()
        pool = NumberPool(client, pool_key=TEST_POOL_KEY)
        try:
            await cleanup(client)
            assert await pool.available() == 0

            await pool.initialize(["+15550008888"])
            assert await pool.available() == 1

            await pool.checkout()
            assert await pool.available() == 0
        finally:
            await cleanup(client)
            await client.aclose()

    run(_test())
