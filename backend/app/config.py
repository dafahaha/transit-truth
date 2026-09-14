"""
Application configuration - 应用配置

所有配置都可以通过环境变量覆盖，便于部署和自定义。

环境变量列表：
- REQUEST_TIMEOUT: 请求超时时间（秒，默认30）
- MAX_RETRIES: 最大重试次数（默认3）
- INITIAL_RETRY_DELAY: 初始重试延迟（秒，默认1.0）
- MAX_RETRY_DELAY: 最大重试延迟（秒，默认30.0）
- CONCURRENT_REQUESTS: 并发请求数（默认5）
- DEFAULT_PROBE_COUNT: 默认探针数量（默认10）
- QUICK_PROBE_COUNT: 快速模式探针数量（默认3）
- DEEP_PROBE_COUNT: 深度模式探针数量（默认10）
- RANDOM_SEED: 随机种子（默认42）
- LOG_LEVEL: 日志级别（默认INFO）
- CIRCUIT_BREAKER_THRESHOLD: 断路器失败阈值（默认10）
- CIRCUIT_BREAKER_TIMEOUT: 断路器恢复超时（秒，默认30）
- DATABASE_PATH: 数据库路径（默认data/transit_truth.db）
"""
import os
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
BENCHMARK_DIR = DATA_DIR / "benchmarks"
RANKING_DIR = DATA_DIR / "rankings"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "transit_truth.db")))

# API settings
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_RETRY_DELAY = float(os.getenv("INITIAL_RETRY_DELAY", "1.0"))
MAX_RETRY_DELAY = float(os.getenv("MAX_RETRY_DELAY", "30.0"))
CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "5"))

# Audit settings
DEFAULT_PROBE_COUNT = int(os.getenv("DEFAULT_PROBE_COUNT", "10"))
QUICK_PROBE_COUNT = int(os.getenv("QUICK_PROBE_COUNT", "3"))
DEEP_PROBE_COUNT = int(os.getenv("DEEP_PROBE_COUNT", "10"))
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))

# Circuit breaker settings
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "10"))
CIRCUIT_BREAKER_TIMEOUT = float(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30.0"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

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


def get_config_summary() -> dict:
    """获取当前配置摘要（用于调试和日志）"""
    return {
        "request_timeout": REQUEST_TIMEOUT,
        "max_retries": MAX_RETRIES,
        "initial_retry_delay": INITIAL_RETRY_DELAY,
        "max_retry_delay": MAX_RETRY_DELAY,
        "concurrent_requests": CONCURRENT_REQUESTS,
        "default_probe_count": DEFAULT_PROBE_COUNT,
        "quick_probe_count": QUICK_PROBE_COUNT,
        "deep_probe_count": DEEP_PROBE_COUNT,
        "circuit_breaker_threshold": CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_timeout": CIRCUIT_BREAKER_TIMEOUT,
        "log_level": LOG_LEVEL,
        "database_path": str(DB_PATH),
    }
