"""TransitTruth model-identity verifier.

Public SDK entry point::

    from app.verify import verify_endpoint
    report = await verify_endpoint(
        base_url="https://relay.example/v1",
        claimed_model="gpt-4o-mini",
    )

The report is a plain JSON-serializable dict. It never contains the API key.
"""

from .core import verify_endpoint

__all__ = ["verify_endpoint"]
