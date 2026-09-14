"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
BENCHMARK_DIR = DATA_DIR / "benchmarks"
RANKING_DIR = DATA_DIR / "rankings"
DB_PATH = DATA_DIR / "transit_truth.db"

# API settings
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "5"))

# Audit settings
DEFAULT_PROBE_COUNT = int(os.getenv("DEFAULT_PROBE_COUNT", "10"))
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))

# Known official API base URLs
OFFICIAL_APIS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
}

# Model families and their known characteristics
MODEL_FAMILIES = {
    "gpt-4": {"family": "openai-gpt4", "tokenizer": "cl100k_base", "tier": "high"},
    "gpt-4o": {"family": "openai-gpt4o", "tokenizer": "o200k_base", "tier": "high"},
    "gpt-4-turbo": {"family": "openai-gpt4", "tokenizer": "cl100k_base", "tier": "high"},
    "gpt-3.5": {"family": "openai-gpt35", "tokenizer": "cl100k_base", "tier": "mid"},
    "gpt-3.5-turbo": {"family": "openai-gpt35", "tokenizer": "cl100k_base", "tier": "mid"},
    "claude-3-opus": {"family": "anthropic-claude3", "tokenizer": "claude", "tier": "high"},
    "claude-3-sonnet": {"family": "anthropic-claude3", "tokenizer": "claude", "tier": "mid"},
    "claude-3-haiku": {"family": "anthropic-claude3", "tokenizer": "claude", "tier": "low"},
    "claude-3.5": {"family": "anthropic-claude35", "tokenizer": "claude", "tier": "high"},
    "gemini-1.5-pro": {"family": "google-gemini", "tokenizer": "gemini", "tier": "high"},
    "gemini-1.5-flash": {"family": "google-gemini", "tokenizer": "gemini", "tier": "mid"},
}
