"""
Contribution API endpoints - 贡献API端点

支持用户通过API提交审计结果、基准数据等贡献。
不需要GitHub账号，只需要提供贡献者信息即可。

设计原则：
- 降低贡献门槛，但不降低贡献质量
- 所有贡献都需要质量审核
- 匿名贡献可接受，但信誉权重低
- 自动检测恶意数据和异常值
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.contributor_reputation import (
    ContributorReputationSystem,
    ContributionType,
    ContributionChannel,
)

router = APIRouter(prefix="/api/contribute", tags=["contribute"])

# 全局贡献者信誉系统实例
_reputation_system = ContributorReputationSystem()


# ─── 请求/响应模型 ────────────────────────────────────

class AuditContributionRequest(BaseModel):
    """审计结果贡献请求"""
    # 审计结果数据
    audit_result: dict = Field(..., description="完整的审计结果JSON")

    # 贡献者信息（可选，不填则为匿名）
    contributor_name: Optional[str] = Field(None, description="贡献者名称（显示用）")
    contributor_email: Optional[str] = Field(None, description="贡献者邮箱（用于联系，不公开）")
    is_anonymous: bool = Field(False, description="是否匿名贡献")

    # 元数据
    relay_name: Optional[str] = Field(None, description="中转站名称（可选，用于排行榜展示）")
    notes: Optional[str] = Field(None, description="备注信息")


class ContributionResponse(BaseModel):
    """贡献响应"""
    success: bool
    contribution_id: Optional[str] = None
    contributor_id: Optional[str] = None
    contributor_name: Optional[str] = None
    is_anonymous: bool = False
    contribution_type: str = "audit"
    channel: str = "api"
    is_valid: bool = False
    quality_score: float = 0.0
    reputation_weight: float = 0.0
    message: str = ""
    next_steps: list[str] = Field(default_factory=list)


class ContributorStatsResponse(BaseModel):
    """贡献者统计响应"""
    contributor_id: str
    contributor_name: str
    contribution_type: str
    level: str
    total_contributions: int
    valid_contributions: int
    reputation_weight: float
    level_progress: dict
    badges: list[str]


# ─── API 端点 ────────────────────────────────────

@router.post("/audit", response_model=ContributionResponse)
async def contribute_audit_result(request: AuditContributionRequest):
    """
    提交审计结果贡献

    - 不需要GitHub账号
    - 支持匿名贡献
    - 自动质量审核
    - 计算信誉权重

    质量审核标准：
    - 必要字段：model, base_url, overall_score
    - 探针数量：>=10为高质量，>=5为中等，<5为低质量
    - 异常检测：明显错误或恶意数据标记为无效
    """
    try:
        # 1. 验证必要字段
        audit = request.audit_result
        required_fields = ["model", "base_url", "overall_score"]
        missing_fields = [f for f in required_fields if f not in audit]
        if missing_fields:
            return ContributionResponse(
                success=False,
                is_valid=False,
                message=f"缺少必要字段: {', '.join(missing_fields)}",
                next_steps=["请确保审计结果包含 model, base_url, overall_score 字段"],
            )

        # 2. 生成贡献者ID
        if request.is_anonymous or not request.contributor_email:
            contributor_id = f"anonymous_{uuid.uuid4().hex[:8]}"
            contributor_name = "匿名用户"
            is_anonymous = True
        else:
            # 用邮箱的hash作为贡献者ID（保护隐私）
            import hashlib
            email_hash = hashlib.sha256(request.contributor_email.encode()).hexdigest()[:12]
            contributor_id = f"user_{email_hash}"
            contributor_name = request.contributor_name or request.contributor_email
            is_anonymous = False

        # 3. 注册贡献者（如果不存在）
        contributor = _reputation_system.register_contributor(
            id=contributor_id,
            name=contributor_name,
            contribution_type=ContributionType.AUDIT,
            channel=ContributionChannel.API,
            is_anonymous=is_anonymous,
        )

        # 4. 计算探针数量（用于质量评分）
        probe_count = 0
        if "checks" in audit:
            probe_count = len(audit["checks"])
        elif "fingerprint" in audit and "probes" in audit["fingerprint"]:
            probe_count = len(audit["fingerprint"]["probes"])

        # 5. 构建贡献内容
        contribution_content = {
            **audit,
            "probe_count": probe_count,
            "relay_name": request.relay_name,
            "notes": request.notes,
            "submitted_at": datetime.now().isoformat(),
        }

        # 6. 添加贡献（自动质量审核）
        contribution = _reputation_system.add_contribution(
            contributor_id=contributor_id,
            contribution_type=ContributionType.AUDIT,
            channel=ContributionChannel.API,
            content=contribution_content,
            auto_validate=True,
        )

        # 7. 计算信誉权重
        reputation_weight = _reputation_system.calculate_audit_result_weight(
            contributor_id=contributor_id,
            audit_result=contribution_content,
        )

        # 8. 构建响应
        if contribution.is_valid:
            message = "贡献成功！审计结果已通过质量审核，将计入排行榜。"
            next_steps = [
                "你可以继续提交更多审计结果",
                "贡献次数达到3次可升级为Silver等级",
                "贡献次数达到10次可升级为Gold等级",
            ]
        else:
            message = "贡献已接收，但需要人工审核后才会计入排行榜。"
            next_steps = [
                "请确保审计结果完整（建议使用深度模式，10+探针）",
                "管理员会在24小时内完成审核",
                "审核通过后会自动计入排行榜",
            ]

        return ContributionResponse(
            success=True,
            contribution_id=contribution.id,
            contributor_id=contributor_id,
            contributor_name=contributor_name,
            is_anonymous=is_anonymous,
            contribution_type="audit",
            channel="api",
            is_valid=contribution.is_valid,
            quality_score=contribution.quality_score,
            reputation_weight=reputation_weight,
            message=message,
            next_steps=next_steps,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"贡献失败: {str(e)}")


@router.get("/contributor/{contributor_id}", response_model=ContributorStatsResponse)
async def get_contributor_stats(contributor_id: str):
    """
    获取贡献者统计信息

    包括：贡献类型、等级、贡献次数、信誉权重、等级进度、徽章
    """
    contributor = _reputation_system.get_contributor(contributor_id)
    if not contributor:
        raise HTTPException(status_code=404, detail="贡献者不存在")

    badges = _reputation_system.get_contributor_badges(contributor_id)

    return ContributorStatsResponse(
        contributor_id=contributor.id,
        contributor_name=contributor.name,
        contribution_type=contributor.contribution_type.value,
        level=contributor.level.value,
        total_contributions=contributor.total_contributions,
        valid_contributions=contributor.valid_contributions,
        reputation_weight=contributor.get_reputation_weight(),
        level_progress=contributor.get_level_progress(),
        badges=badges,
    )


@router.get("/top-contributors")
async def get_top_contributors(
    contribution_type: Optional[str] = None,
    limit: int = 10,
):
    """
    获取Top贡献者列表

    参数：
    - contribution_type: 筛选贡献类型（code/data/audit/doc/community），不填则返回所有类型
    - limit: 返回数量，默认10
    """
    try:
        ctype = ContributionType(contribution_type) if contribution_type else None
        contributors = _reputation_system.get_top_contributors(
            contribution_type=ctype,
            limit=limit,
        )

        return {
            "contributors": [
                {
                    **c.to_dict(),
                    "badges": _reputation_system.get_contributor_badges(c.id),
                }
                for c in contributors
            ],
            "total": len(contributors),
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的贡献类型: {contribution_type}，可选值: code, data, audit, doc, community",
        )


@router.get("/channels")
async def list_contribution_channels():
    """
    列出所有支持的贡献渠道

    包括：GitHub PR/Issue、在线表单、邮件、社区、API、Gitee
    """
    channels = [
        {
            "id": "github_pr",
            "name": "GitHub PR",
            "description": "提交代码、文档、基准数据（适合技术用户）",
            "difficulty": "advanced",
            "requires_github": True,
            "url": "https://github.com/dafahaha/transit-truth/pulls",
        },
        {
            "id": "github_issue",
            "name": "GitHub Issue",
            "description": "提交审计结果、报告Bug（有GitHub账号的用户）",
            "difficulty": "intermediate",
            "requires_github": True,
            "url": "https://github.com/dafahaha/transit-truth/issues/new",
        },
        {
            "id": "online_form",
            "name": "在线表单",
            "description": "在在线Demo中一键贡献审计结果（推荐普通用户）",
            "difficulty": "beginner",
            "requires_github": False,
            "url": "https://dafahaha.github.io/transit-truth/",
        },
        {
            "id": "email",
            "name": "邮件提交",
            "description": "把审计结果JSON发到指定邮箱（零门槛）",
            "difficulty": "beginner",
            "requires_github": False,
            "email": "contribute@transit-truth.xxx",
        },
        {
            "id": "community",
            "name": "社区提交",
            "description": "在微信群/QQ群/知乎评论区提交（社区活跃用户）",
            "difficulty": "beginner",
            "requires_github": False,
        },
        {
            "id": "api",
            "name": "API 提交",
            "description": "通过REST API批量提交（高级用户）",
            "difficulty": "advanced",
            "requires_github": False,
            "endpoint": "POST /api/contribute/audit",
        },
        {
            "id": "gitee",
            "name": "Gitee",
            "description": "通过Gitee镜像仓库提交（国内用户）",
            "difficulty": "intermediate",
            "requires_github": False,
            "url": "https://gitee.com/dafahaha/transit-truth",
        },
    ]

    return {
        "channels": channels,
        "total": len(channels),
        "recommendation": "如果你是普通用户，推荐使用「在线表单」；如果你是技术用户，推荐使用「GitHub PR」。",
    }
