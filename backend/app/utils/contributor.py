"""One-click contribution to the public ranking.

Allows users to contribute audit results to the public ranking
by automatically creating a GitHub Issue with the audit_result template.

Two modes:
1. Server-side: backend uses configured GitHub token to create issues
2. Client-side: frontend uses user's GitHub token via GitHub API

Security:
- GitHub tokens are never stored on the server (client-side mode)
- Server-side mode requires explicit configuration and is opt-in
- All contributions are publicly visible as GitHub Issues
"""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


GITHUB_API_BASE = "https://api.github.com"
DEFAULT_REPO = "dafahaha/transit-truth"


@dataclass
class ContributionResult:
    """Result of a contribution attempt."""
    success: bool
    issue_url: Optional[str] = None
    issue_number: Optional[int] = None
    error: Optional[str] = None


class GitHubContributor:
    """Create GitHub Issues for audit result contributions."""

    def __init__(self, github_token: str, repo: str = DEFAULT_REPO):
        self.github_token = github_token
        self.repo = repo
        self.headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    async def contribute_audit(self, audit_result: dict,
                                 contributor_name: Optional[str] = None,
                                 anonymous: bool = False,
                                 labels: Optional[list[str]] = None) -> ContributionResult:
        """Contribute an audit result by creating a GitHub Issue.

        Args:
            audit_result: The full audit result dictionary
            contributor_name: GitHub username (for attribution)
            anonymous: If True, contributor is listed as "anonymous"
            labels: Additional labels to add

        Returns:
            ContributionResult with issue URL or error
        """
        # Build issue title
        relay = audit_result.get("relay_name", "unknown")
        model = audit_result.get("model", "unknown")
        score = audit_result.get("overall_score", 0)
        title = f"[audit-result] {relay} / {model} - {score}分"

        # Build issue body from template
        body = self._build_issue_body(audit_result, contributor_name, anonymous)

        # Default labels
        default_labels = ["audit-result", "needs-review"]
        if labels:
            default_labels.extend(labels)

        # Create issue via GitHub API
        url = f"{GITHUB_API_BASE}/repos/{self.repo}/issues"
        payload = {
            "title": title,
            "body": body,
            "labels": default_labels,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self.headers, json=payload)

            if response.status_code == 201:
                data = response.json()
                return ContributionResult(
                    success=True,
                    issue_url=data.get("html_url"),
                    issue_number=data.get("number"),
                )
            elif response.status_code == 401:
                return ContributionResult(
                    success=False,
                    error="GitHub token 无效或已过期，请检查 token 权限（需要 repo 权限）",
                )
            elif response.status_code == 403:
                return ContributionResult(
                    success=False,
                    error="GitHub API 速率限制或权限不足，请稍后重试",
                )
            elif response.status_code == 422:
                return ContributionResult(
                    success=False,
                    error=f"提交内容验证失败: {response.text[:200]}",
                )
            else:
                return ContributionResult(
                    success=False,
                    error=f"GitHub API 返回 {response.status_code}: {response.text[:200]}",
                )
        except httpx.TimeoutException:
            return ContributionResult(
                success=False,
                error="连接 GitHub 超时，请检查网络连接",
            )
        except Exception as e:
            return ContributionResult(
                success=False,
                error=f"创建 Issue 失败: {str(e)}",
            )

    def _build_issue_body(self, audit_result: dict,
                            contributor_name: Optional[str],
                            anonymous: bool) -> str:
        """Build GitHub Issue body from audit result template."""
        tc = audit_result.get("token_comparison", {}) or {}
        fp = audit_result.get("fingerprint", {}) or {}
        lat = audit_result.get("latency", {}) or {}

        contributor = "匿名" if anonymous else (contributor_name or "匿名")

        # Truncate JSON for the issue body (GitHub has 65536 char limit)
        audit_json = json.dumps(audit_result, indent=2, ensure_ascii=False)
        if len(audit_json) > 30000:
            audit_json = audit_json[:30000] + "\n... (truncated)"

        body = f"""## 审计结果

### 基本信息
- **中转站**: {audit_result.get('relay_name', 'N/A')}
- **Base URL**: {audit_result.get('base_url', 'N/A')}
- **模型**: {audit_result.get('model', 'N/A')}
- **审计模式**: {audit_result.get('mode', 'N/A')}
- **审计时间**: {audit_result.get('timestamp', datetime.now().isoformat())}
- **贡献者**: {contributor}

### 评分
- **信任分**: {audit_result.get('overall_score', 'N/A')}/100
- **信任等级**: {audit_result.get('trust_level', 'N/A')}

### Token 对比
- 报告 Prompt Tokens: {tc.get('prompt_tokens_reported', 'N/A')}
- 预期 Prompt Tokens: {tc.get('prompt_tokens_expected', 'N/A')}
- Token 差异率: {tc.get('prompt_inflation_pct', 'N/A')}
- Chat Template 估算: {tc.get('chat_template_overhead', 'N/A')} tokens
- 可疑: {'是' if tc.get('suspicious') else '否'}

### 模型指纹
- 声称模型: {fp.get('claimed_model', 'N/A')}
- 检测家族: {fp.get('detected_family', 'N/A')}
- 家族匹配: {'是' if fp.get('family_match') else '否'}
- 置信度: {fp.get('confidence', 'N/A')}
- 能力测试: {fp.get('capability', {}).get('passed', 'N/A')}/{fp.get('capability', {}).get('total', 'N/A')} 通过

### 延迟与协议
- 平均延迟: {lat.get('avg_latency_ms', 'N/A')}ms
- 协议通过率: {lat.get('protocol_pass_rate', 'N/A')}

### 原始 JSON
```json
{audit_json}
```

---
*由 TransitTruth 自动生成 · 一键贡献功能*
"""
        return body

    async def verify_token(self) -> bool:
        """Verify that the GitHub token is valid."""
        url = f"{GITHUB_API_BASE}/user"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers)
            return response.status_code == 200
        except Exception:
            return False


# ─── Convenience functions ────────────────────────────────────

async def contribute_audit_result(audit_result: dict,
                                    github_token: str,
                                    contributor_name: Optional[str] = None,
                                    anonymous: bool = False,
                                    repo: str = DEFAULT_REPO) -> ContributionResult:
    """One-click contribute an audit result to the public ranking.

    Usage:
        result = await contribute_audit_result(
            audit_result=my_audit_dict,
            github_token="ghp_xxx",
            contributor_name="@dafahaha",
        )
        if result.success:
            print(f"Contributed: {result.issue_url}")
    """
    contributor = GitHubContributor(github_token, repo)
    return await contributor.contribute_audit(
        audit_result=audit_result,
        contributor_name=contributor_name,
        anonymous=anonymous,
    )
