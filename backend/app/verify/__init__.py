"""TransitTruth model-identity verifier.

Public SDK entry point::

    from app.verify import verify_endpoint, verify_endpoint_sync

    # async
    report = await verify_endpoint(
        base_url="https://relay.example/v1",
        claimed_model="gpt-4o-mini",
    )

    # synchronous convenience wrapper
    report = verify_endpoint_sync(base_url=..., claimed_model=...)

The report is a plain JSON-serializable dict. It never contains the API key.
"""

from __future__ import annotations

import asyncio

from .core import verify_endpoint

__all__ = ["verify_endpoint", "verify_endpoint_sync"]


def verify_endpoint_sync(*args, **kwargs) -> dict:
    """Synchronous wrapper around :func:`verify_endpoint` (runs its own loop)."""
    return asyncio.run(verify_endpoint(*args, **kwargs))
