"""Offline o200k token-count "caliber lock" for the gpt-4o / gpt-4o-mini baselines.

The probe battery sends ``messages=[system, user]`` for EVERY probe
(``battery.py``). The shipped gpt-4o / gpt-4o-mini baselines were originally
collected with a user-only message, so their ``prompt_tokens`` values were
systematically ~16 tokens below what a real endpoint reports for the battery's
actual request -- a genuine gpt-4o-mini endpoint was then flagged
``suspicious`` by ``tokenizer_consistency``.

v0.4.4 recomputes those baseline counts OFFLINE with tiktoken (no API key,
counting only) using the EXACT same definition the battery sends. This module is
the single source of that definition: the baseline-regeneration script and the
"caliber lock" test both call it, so the baseline numbers and the test can never
drift apart again.
"""

from __future__ import annotations

import tiktoken

from ..core.probes import TOKENIZER_PROBES

# OpenAI chat-completions count prompt tokens over the concatenation of the
# message contents the reference-server also uses (system + "\n" + user).
_O200K = tiktoken.get_encoding("o200k_base")


def battery_request_text(system_prompt: str, user_prompt: str) -> str:
    """Plain-text form of the battery's ``messages=[system, user]`` request.

    Deliberately matches ``ReferenceBackend.prompt_tokens`` (``"\n".join`` of the
    message contents), so a self-hosted reference server and the offline
    o200k baseline count the same prompt identically.
    """
    return system_prompt + "\n" + user_prompt


def o200k_prompt_tokens(system_prompt: str, user_prompt: str) -> int:
    """Offline o200k count of the battery's exact system+user prompt."""
    return len(_O200K.encode(battery_request_text(system_prompt, user_prompt)))


def expected_battery_tokenizer_counts() -> dict[str, int]:
    """Map ``tokenizer_probe_id`` -> offline o200k prompt-token count.

    This is what a real gpt-4o / gpt-4o-mini endpoint must self-report for the
    battery's system+user request.
    """
    return {
        p.id: o200k_prompt_tokens(p.system_prompt, p.prompt) for p in TOKENIZER_PROBES
    }
