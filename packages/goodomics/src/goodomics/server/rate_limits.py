"""Asynchronous request and concurrency limits for login and AI endpoints."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request
from limits import parse
from limits.aio.storage import MemoryStorage, RedisStorage
from limits.aio.strategies import MovingWindowRateLimiter

from goodomics.server.auth import Principal
from goodomics.server.settings import RateLimitSettings, Settings


class AsyncRateLimiter:
    """Small async limiter using ``limits`` policy parsing and in-memory state."""

    def __init__(self, settings: RateLimitSettings) -> None:
        self.settings = settings
        self._active: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = asyncio.Lock()

        backend = settings.backend_uri

        if backend == "memory://":
            storage = MemoryStorage()
        elif backend.startswith(("redis://", "rediss://", "valkey://")):
            storage = RedisStorage(backend.replace("valkey://", "redis://", 1))
        else:
            raise ValueError(
                "Rate-limit backend must be memory://, redis://, rediss://, or valkey://"
            )

        self._strategy = MovingWindowRateLimiter(storage)

    async def check(self, namespace: str, key: str, policies: list[str]) -> None:
        """Check the rate limit for the given namespace, key, and policies."""

        for policy in policies:
            item = parse(policy)
            if not await self._strategy.hit(item, namespace, key):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(item.get_expiry())},
                )

    @asynccontextmanager
    async def concurrent(
        self, namespace: str, key: str, maximum: int
    ) -> AsyncIterator[None]:
        """
        Context manager to enforce a concurrent request limit
        for the given namespace and key.
        """

        active_key = (namespace, key)
        async with self._lock:
            if self._active[active_key] >= maximum:
                raise HTTPException(
                    status_code=429,
                    detail="Concurrent request limit exceeded",
                    headers={"Retry-After": "1"},
                )
            self._active[active_key] += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active[active_key] = max(0, self._active[active_key] - 1)


def client_ip(request: Request, settings: Settings) -> str:
    """Resolve a client address without trusting spoofable forwarded headers."""

    peer = request.client.host if request.client else "unknown"
    if peer in settings.server.trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return peer


def principal_rate_key(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, Principal) and principal.user_id:
        return principal.user_id
    return client_ip(request, request.app.state.settings)
