"""Self-hosted, OpenAI-compatible reference backend.

Run a local service that mimics an OpenAI-compatible endpoint so a user can
generate / compare reference fingerprints WITHOUT paying a cloud provider:

    transit-truth reference-server --model qwen2.5-0.5b-instruct --port 8765

Honesty contract:
- The ``usage.prompt_tokens`` it returns are computed by the REAL local tokenizer
  (downloaded via HF_ENDPOINT, default hf-mirror). This is real tokenizer
  fingerprint behavior.
- The generated ``content`` for behavioral probes is a DETERMINISTIC STUB, not a
  real model generation. When no tokenizer is available, the whole service runs
  as an explicitly-labeled "plumbing stub". It is never presented as a real model.
"""

from __future__ import annotations

import hashlib
import os

from fastapi import FastAPI, Request

# model name shipped in the fingerprint catalog -> HF tokenizer repo
CATALOG_TOKENIZERS: dict[str, str] = {
    "qwen2.5-0.5b-instruct": "Qwen/Qwen2.5-0.5B-Instruct",
    "glm-4-9b-chat": "THUDM/glm-4-9b-chat",
    "deepseek-r1-distill-qwen-1.5b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
}


class ReferenceBackend:
    """Wraps a real tokenizer (or a stub) behind an OpenAI-compatible shape."""

    def __init__(self, model: str):
        self.model = model
        self.tokenizer_repo = CATALOG_TOKENIZERS.get(model)
        self._tokenizer = None
        self.mode = "stub"  # upgraded to "tokenizer" on success

    def load(self) -> str:
        """Lazily load the real tokenizer. Returns the operational mode."""
        if self._tokenizer is not None:
            return self.mode
        if self.tokenizer_repo is None:
            self.mode = "stub"
            return self.mode
        try:
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from tokenizers import Tokenizer  # lazy heavy import

            self._tokenizer = Tokenizer.from_pretrained(self.tokenizer_repo)
            self.mode = "tokenizer"
        except Exception:  # noqa: BLE001 - any download/parse issue -> honest stub
            self._tokenizer = None
            self.mode = "stub"
        return self.mode

    def prompt_tokens(self, messages: list[dict]) -> int:
        """Real prompt-token count (deterministic) or a stub placeholder."""
        text = "\n".join(str(m.get("content", "")) for m in messages)
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text).ids)
        # Plumbing stub: a stable placeholder so the API shape still works.
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % 40 + 10

    def stub_content(self, messages: list[dict]) -> str:
        """Deterministic, clearly-labeled stub generation (NOT a real model)."""
        text = "\n".join(str(m.get("content", "")) for m in messages)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        # 1..6 deterministic bucket -> mimics a fixed behavioral bias.
        bucket = int(h[0], 16) % 6
        return f"stub-{self.model}-{bucket}"


def build_app(model: str) -> tuple:
    """Build a FastAPI app for the given reference model (test-server style).

    Returns ``(app, backend)``. FastAPI/Request are imported at module level on
    purpose: with ``from __future__ import annotations`` a function-level import
    left ``Request`` unresolvable at route-registration time, which made FastAPI
    treat ``request: Request`` as a *required query param* and every
    ``/v1/chat/completions`` POST return 422.
    """
    backend = ReferenceBackend(model)
    mode = backend.load()

    app = FastAPI(title=f"TransitTruth reference-server ({model})")

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": model,
                    "object": "model",
                    "mode": mode,
                    "note": (
                        "real tokenizer fingerprint; behavioral content is a stub"
                        if mode == "tokenizer"
                        else "PLUMBING STUB: no real tokenizer/model loaded"
                    ),
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        pt = backend.prompt_tokens(messages)
        return {
            "id": f"chatcmpl-ref-{model}",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": backend.stub_content(messages),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": 2,
                "total_tokens": pt + 2,
            },
            "_reference_server": {"model": model, "mode": mode},
        }

    return app, backend
