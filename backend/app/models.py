"""Data models for audit results."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class AuditStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckType(str, Enum):
    TOKEN_COUNT = "token_count"
    MODEL_FINGERPRINT = "model_fingerprint"
    RESPONSE_LATENCY = "response_latency"
    PROTOCOL_COMPLIANCE = "protocol_compliance"
    CAPABILITY_TEST = "capability_test"


class CheckResult(BaseModel):
    """Result of a single check."""
    check_type: CheckType
    name: str
    passed: bool
    score: float = Field(ge=0, le=100, description="Score 0-100")
    details: str
    evidence: dict = Field(default_factory=dict)
    duration_ms: float = 0


class TokenComparison(BaseModel):
    """Token count comparison result.

    Note: "inflation_pct" fields are named for backward compatibility but
    represent "discrepancy" — the difference may include legitimate chat
    template overhead. See discrepancy_note for details.
    """
    prompt_tokens_reported: int
    prompt_tokens_expected: Optional[int] = None
    completion_tokens_reported: int
    completion_tokens_expected: Optional[int] = None
    total_tokens_reported: int
    prompt_inflation_pct: Optional[float] = None
    completion_inflation_pct: Optional[float] = None
    suspicious: bool = False
    discrepancy_note: str = ""
    chat_template_overhead: int = 0


class FingerprintResult(BaseModel):
    """Model fingerprint result."""
    claimed_model: str
    detected_family: Optional[str] = None
    family_match: bool
    confidence: float = Field(ge=0, le=1)
    tokenizer_signature: dict = Field(default_factory=dict)
    behavioral_signature: dict = Field(default_factory=dict)
    suspicious: bool = False


class AuditMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


class AuditRequest(BaseModel):
    """Request to start an audit."""
    api_key: str = Field(..., description="API key for the relay service")
    base_url: str = Field(..., description="Base URL of the relay API")
    model: str = Field(..., description="Model name to audit")
    official_api_key: Optional[str] = Field(None, description="Official API key for comparison (optional)")
    mode: AuditMode = Field(default=AuditMode.DEEP, description="Audit mode: quick (3 probes, ~10s) or deep (10 probes, ~60s)")
    probe_count: Optional[int] = Field(None, ge=1, le=50, description="Override probe count (optional, uses mode default if not set)")
    run_token_check: bool = True
    run_fingerprint: bool = True
    run_latency: bool = True
    run_protocol: bool = True


class AuditResult(BaseModel):
    """Complete audit result."""
    audit_id: str
    status: AuditStatus
    model: str
    base_url: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    overall_score: float = Field(ge=0, le=100, default=0)
    trust_level: str = "unknown"  # high / medium / low / critical
    checks: list[CheckResult] = Field(default_factory=list)
    token_comparison: Optional[TokenComparison] = None
    fingerprint: Optional[FingerprintResult] = None
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class RankingEntry(BaseModel):
    """Entry in the public ranking."""
    relay_name: str
    base_url: str
    model: str
    avg_trust_score: float
    audit_count: int
    last_audited: datetime
    token_inflation_avg: float = 0
    model_authenticity_rate: float = 0
    avg_latency_ms: float = 0
    uptime_rate: float = 0
    notes: str = ""
