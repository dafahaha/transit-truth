"""
分层贡献者信誉系统 (Tiered Contributor Reputation System)

解决两个关键问题：
1. 没有GitHub账号/不能访问外网的用户如何贡献
2. 如何避免贡献者价值稀释（代码贡献者 vs 审计贡献者）

设计原则：
- 降低贡献门槛，但不降低贡献质量
- 分层贡献者，不同类型独立计算等级
- 匿名贡献可接受，但信誉权重低
- 多渠道贡献（GitHub/在线表单/邮件/社区/API）
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ContributionType(Enum):
    """贡献类型"""
    CODE = "code"           # 代码贡献：PR被合并
    DATA = "data"           # 基准数据贡献：模型基准数据被采纳
    AUDIT = "audit"         # 审计结果贡献：中转站审计结果
    DOC = "doc"             # 文档贡献：文档PR被合并
    COMMUNITY = "community" # 社区贡献：回答问题、推广项目


class ContributorLevel(Enum):
    """贡献者等级（每个类型独立计算）"""
    BRONZE = "bronze"       # 青铜：首次贡献
    SILVER = "silver"       # 白银：3次有效贡献
    GOLD = "gold"           # 黄金：10次有效贡献
    PLATINUM = "platinum"   # 白金：30次有效贡献 + 质量审核
    DIAMOND = "diamond"     # 钻石：100次有效贡献 + 核心贡献者认可


class ContributionChannel(Enum):
    """贡献渠道"""
    GITHUB_ISSUE = "github_issue"     # GitHub Issue（技术用户）
    GITHUB_PR = "github_pr"           # GitHub PR（代码/文档/数据）
    ONLINE_FORM = "online_form"       # 在线表单（普通用户）
    EMAIL = "email"                   # 邮件提交（最简单）
    COMMUNITY = "community"           # 社区提交（微信群/QQ群/评论区）
    API = "api"                       # API批量提交（高级用户）
    GITEE = "gitee"                   # Gitee（国内用户）


# 贡献类型对应的信誉权重（影响审计结果的可信度）
CONTRIBUTION_TYPE_WEIGHT = {
    ContributionType.CODE: 1.5,        # 代码贡献者最可信
    ContributionType.DATA: 1.2,        # 基准数据贡献者次可信
    ContributionType.DOC: 1.1,         # 文档贡献者
    ContributionType.COMMUNITY: 1.0,   # 社区贡献者
    ContributionType.AUDIT: 1.0,       # 审计贡献者（普通注册用户）
}

# 等级对应的信誉权重乘数
LEVEL_WEIGHT_MULTIPLIER = {
    ContributorLevel.BRONZE: 0.8,
    ContributorLevel.SILVER: 1.0,
    ContributorLevel.GOLD: 1.2,
    ContributorLevel.PLATINUM: 1.4,
    ContributorLevel.DIAMOND: 1.6,
}

# 等级升级所需的有效贡献次数
LEVEL_THRESHOLDS = {
    ContributorLevel.BRONZE: 1,
    ContributorLevel.SILVER: 3,
    ContributorLevel.GOLD: 10,
    ContributorLevel.PLATINUM: 30,
    ContributorLevel.DIAMOND: 100,
}

# 匿名用户的信誉权重
ANONYMOUS_WEIGHT = 0.5

# 新用户（<3次贡献）的信誉权重
NEW_USER_WEIGHT = 0.3


@dataclass
class Contributor:
    """贡献者信息"""
    id: str                                    # 唯一标识（GitHub用户名/邮箱/匿名ID）
    name: str                                  # 显示名称
    contribution_type: ContributionType        # 主要贡献类型
    level: ContributorLevel = ContributorLevel.BRONZE
    channel: ContributionChannel = ContributionChannel.GITHUB_ISSUE
    is_anonymous: bool = False
    is_core_maintainer: bool = False          # 核心维护者
    total_contributions: int = 0              # 总贡献次数
    valid_contributions: int = 0              # 有效贡献次数
    first_contribution_at: Optional[datetime] = None
    last_contribution_at: Optional[datetime] = None
    badges: list[str] = field(default_factory=list)  # 徽章列表

    def get_reputation_weight(self) -> float:
        """计算贡献者的信誉权重"""
        # 核心维护者权重最高
        if self.is_core_maintainer:
            return 2.0

        # 匿名用户权重低
        if self.is_anonymous:
            return ANONYMOUS_WEIGHT

        # 新用户权重低
        if self.valid_contributions < 3:
            return NEW_USER_WEIGHT

        # 基础权重 = 贡献类型权重 × 等级权重乘数
        base_weight = CONTRIBUTION_TYPE_WEIGHT.get(self.contribution_type, 1.0)
        level_multiplier = LEVEL_WEIGHT_MULTIPLIER.get(self.level, 1.0)
        return base_weight * level_multiplier

    def get_level_progress(self) -> dict:
        """获取等级进度"""
        current_threshold = LEVEL_THRESHOLDS.get(self.level, 1)
        next_level = self._get_next_level()
        next_threshold = LEVEL_THRESHOLDS.get(next_level, current_threshold) if next_level else None

        progress = min(1.0, self.valid_contributions / current_threshold) if current_threshold > 0 else 1.0

        return {
            "current_level": self.level.value,
            "current_threshold": current_threshold,
            "valid_contributions": self.valid_contributions,
            "progress": progress,
            "next_level": next_level.value if next_level else None,
            "next_threshold": next_threshold,
            "contributions_to_next": (next_threshold - self.valid_contributions) if next_threshold else 0,
        }

    def _get_next_level(self) -> Optional[ContributorLevel]:
        """获取下一个等级"""
        levels = list(ContributorLevel)
        current_index = levels.index(self.level)
        if current_index < len(levels) - 1:
            return levels[current_index + 1]
        return None

    def check_level_up(self) -> Optional[ContributorLevel]:
        """检查是否可以升级，如果可以返回新等级"""
        next_level = self._get_next_level()
        if not next_level:
            return None

        next_threshold = LEVEL_THRESHOLDS.get(next_level, float('inf'))
        if self.valid_contributions >= next_threshold:
            # Platinum和Diamond需要额外条件
            if next_level == ContributorLevel.PLATINUM:
                # 需要质量审核通过（这里简化处理，实际需要人工审核）
                return next_level if self.valid_contributions >= next_threshold else None
            elif next_level == ContributorLevel.DIAMOND:
                # 需要核心贡献者认可（这里简化处理）
                return next_level if self.is_core_maintainer else None
            return next_level
        return None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "contribution_type": self.contribution_type.value,
            "level": self.level.value,
            "channel": self.channel.value,
            "is_anonymous": self.is_anonymous,
            "is_core_maintainer": self.is_core_maintainer,
            "total_contributions": self.total_contributions,
            "valid_contributions": self.valid_contributions,
            "first_contribution_at": self.first_contribution_at.isoformat() if self.first_contribution_at else None,
            "last_contribution_at": self.last_contribution_at.isoformat() if self.last_contribution_at else None,
            "badges": self.badges,
            "reputation_weight": self.get_reputation_weight(),
            "level_progress": self.get_level_progress(),
        }


@dataclass
class Contribution:
    """单次贡献记录"""
    id: str
    contributor_id: str
    contribution_type: ContributionType
    channel: ContributionChannel
    content: dict                           # 贡献内容（审计结果/基准数据/PR信息等）
    created_at: datetime = field(default_factory=datetime.now)
    is_valid: bool = False                  # 是否通过质量审核
    reviewed_by: Optional[str] = None      # 审核人
    reviewed_at: Optional[datetime] = None
    quality_score: float = 0.0             # 质量评分（0-1）
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "contributor_id": self.contributor_id,
            "contribution_type": self.contribution_type.value,
            "channel": self.channel.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "is_valid": self.is_valid,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "quality_score": self.quality_score,
            "notes": self.notes,
        }


class ContributorReputationSystem:
    """贡献者信誉系统（主类）"""

    def __init__(self):
        self.contributors: dict[str, Contributor] = {}
        self.contributions: list[Contribution] = []

    def register_contributor(self,
                               id: str,
                               name: str,
                               contribution_type: ContributionType,
                               channel: ContributionChannel = ContributionChannel.ONLINE_FORM,
                               is_anonymous: bool = False) -> Contributor:
        """注册新贡献者"""
        if id in self.contributors:
            return self.contributors[id]

        contributor = Contributor(
            id=id,
            name=name,
            contribution_type=contribution_type,
            channel=channel,
            is_anonymous=is_anonymous,
            first_contribution_at=datetime.now(),
        )
        self.contributors[id] = contributor
        return contributor

    def add_contribution(self,
                          contributor_id: str,
                          contribution_type: ContributionType,
                          channel: ContributionChannel,
                          content: dict,
                          auto_validate: bool = True) -> Contribution:
        """添加贡献记录"""
        # 确保贡献者存在
        if contributor_id not in self.contributors:
            raise ValueError(f"Contributor {contributor_id} not found")

        contributor = self.contributors[contributor_id]
        contribution_id = f"contrib_{len(self.contributions) + 1}"

        contribution = Contribution(
            id=contribution_id,
            contributor_id=contributor_id,
            contribution_type=contribution_type,
            channel=channel,
            content=content,
        )

        # 自动质量审核（简化版）
        if auto_validate:
            contribution.is_valid = self._auto_validate(contribution)
            contribution.quality_score = self._calculate_quality_score(contribution)
            contribution.reviewed_at = datetime.now()

        # 更新贡献者统计
        contributor.total_contributions += 1
        contributor.last_contribution_at = datetime.now()
        if contribution.is_valid:
            contributor.valid_contributions += 1
            # 检查升级
            new_level = contributor.check_level_up()
            if new_level:
                contributor.level = new_level

        self.contributions.append(contribution)
        return contribution

    def _auto_validate(self, contribution: Contribution) -> bool:
        """自动质量审核（简化版）"""
        content = contribution.content

        if contribution.contribution_type == ContributionType.AUDIT:
            # 审计结果审核：检查必要字段
            required_fields = ["model", "base_url", "overall_score"]
            return all(field in content for field in required_fields)

        elif contribution.contribution_type == ContributionType.DATA:
            # 基准数据审核：检查样本量
            sample_size = content.get("sample_size", 0)
            return sample_size >= 50

        elif contribution.contribution_type == ContributionType.CODE:
            # 代码贡献：PR被合并即有效
            return content.get("merged", False)

        elif contribution.contribution_type == ContributionType.DOC:
            # 文档贡献：PR被合并即有效
            return content.get("merged", False)

        return True

    def _calculate_quality_score(self, contribution: Contribution) -> float:
        """计算质量评分（0-1）"""
        content = contribution.content

        if contribution.contribution_type == ContributionType.AUDIT:
            # 审计结果质量：探针数量越多质量越高
            probe_count = content.get("probe_count", 0)
            if probe_count >= 10:
                return 1.0
            elif probe_count >= 5:
                return 0.7
            else:
                return 0.4

        elif contribution.contribution_type == ContributionType.DATA:
            # 基准数据质量：样本量越多质量越高
            sample_size = content.get("sample_size", 0)
            if sample_size >= 200:
                return 1.0
            elif sample_size >= 100:
                return 0.8
            elif sample_size >= 50:
                return 0.6
            else:
                return 0.3

        return 0.5

    def get_contributor(self, contributor_id: str) -> Optional[Contributor]:
        """获取贡献者信息"""
        return self.contributors.get(contributor_id)

    def get_top_contributors(self,
                               contribution_type: Optional[ContributionType] = None,
                               limit: int = 10) -> list[Contributor]:
        """获取Top贡献者"""
        contributors = list(self.contributors.values())

        if contribution_type:
            contributors = [c for c in contributors if c.contribution_type == contribution_type]

        # 按有效贡献次数排序
        contributors.sort(key=lambda c: c.valid_contributions, reverse=True)
        return contributors[:limit]

    def get_contributor_badges(self, contributor_id: str) -> list[str]:
        """获取贡献者的徽章列表"""
        contributor = self.contributors.get(contributor_id)
        if not contributor:
            return []

        badges = []

        # 核心维护者徽章
        if contributor.is_core_maintainer:
            badges.append("👑 核心维护者")

        # 贡献类型徽章
        type_badges = {
            ContributionType.CODE: "💻 代码贡献者",
            ContributionType.DATA: "📊 数据贡献者",
            ContributionType.AUDIT: "🔍 审计贡献者",
            ContributionType.DOC: "📝 文档贡献者",
            ContributionType.COMMUNITY: "🌐 社区贡献者",
        }
        if contributor.contribution_type in type_badges:
            badges.append(type_badges[contributor.contribution_type])

        # 等级徽章
        level_badges = {
            ContributorLevel.BRONZE: "🟤 Bronze",
            ContributorLevel.SILVER: "⚪ Silver",
            ContributorLevel.GOLD: "🟡 Gold",
            ContributorLevel.PLATINUM: "🔵 Platinum",
            ContributorLevel.DIAMOND: "💎 Diamond",
        }
        if contributor.level in level_badges:
            badges.append(level_badges[contributor.level])

        # 早期贡献者徽章（30天内）
        if contributor.first_contribution_at:
            days_since_first = (datetime.now() - contributor.first_contribution_at).days
            if days_since_first <= 30:
                badges.append("🚀 早期贡献者")

        return badges

    def calculate_audit_result_weight(self, contributor_id: str, audit_result: dict) -> float:
        """计算审计结果的最终信誉权重"""
        contributor = self.contributors.get(contributor_id)

        # 匿名或不存在的贡献者
        if not contributor or contributor.is_anonymous:
            base_weight = ANONYMOUS_WEIGHT
        else:
            base_weight = contributor.get_reputation_weight()

        # 数据质量分
        probe_count = audit_result.get("probe_count", 0)
        if probe_count >= 10:
            quality_multiplier = 1.0
        elif probe_count >= 5:
            quality_multiplier = 0.7
        else:
            quality_multiplier = 0.4

        return base_weight * quality_multiplier


# ─── 便捷函数 ────────────────────────────────────

def create_default_system() -> ContributorReputationSystem:
    """创建默认的贡献者信誉系统"""
    return ContributorReputationSystem()


def get_contribution_type_display(contribution_type: ContributionType) -> str:
    """获取贡献类型的显示名称"""
    display_names = {
        ContributionType.CODE: "代码贡献者",
        ContributionType.DATA: "基准数据贡献者",
        ContributionType.AUDIT: "审计结果贡献者",
        ContributionType.DOC: "文档贡献者",
        ContributionType.COMMUNITY: "社区贡献者",
    }
    return display_names.get(contribution_type, contribution_type.value)


def get_channel_display(channel: ContributionChannel) -> str:
    """获取贡献渠道的显示名称"""
    display_names = {
        ContributionChannel.GITHUB_ISSUE: "GitHub Issue",
        ContributionChannel.GITHUB_PR: "GitHub PR",
        ContributionChannel.ONLINE_FORM: "在线表单",
        ContributionChannel.EMAIL: "邮件提交",
        ContributionChannel.COMMUNITY: "社区提交",
        ContributionChannel.API: "API提交",
        ContributionChannel.GITEE: "Gitee",
    }
    return display_names.get(channel, channel.value)
