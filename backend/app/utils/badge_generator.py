"""Generate contributor badges as SVG.

Badges can be embedded in GitHub Profile READMEs to show
TransitTruth contribution status.
"""
from __future__ import annotations


def generate_contributor_badge(username: str, audit_count: int, verified_count: int = 0) -> str:
    """Generate a contributor badge SVG.

    Args:
        username: GitHub username (without @)
        audit_count: Number of audits contributed
        verified_count: Number of verified audits

    Returns:
        SVG string
    """
    # Determine badge level
    if audit_count >= 20:
        level = "Platinum"
        color = "#e5e4e2"
        bg_color = "#1e293b"
    elif audit_count >= 10:
        level = "Gold"
        color = "#ffd700"
        bg_color = "#1e293b"
    elif audit_count >= 5:
        level = "Silver"
        color = "#c0c0c0"
        bg_color = "#1e293b"
    elif audit_count >= 1:
        level = "Bronze"
        color = "#cd7f32"
        bg_color = "#1e293b"
    else:
        level = "Contributor"
        color = "#94a3b8"
        bg_color = "#1e293b"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="80" viewBox="0 0 320 80">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{bg_color};stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0f172a;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="320" height="80" rx="12" fill="url(#bg)"/>
  <circle cx="40" cy="40" r="22" fill="{color}" opacity="0.2"/>
  <text x="40" y="47" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="bold" fill="{color}">🛡</text>
  <text x="72" y="32" font-family="Arial, sans-serif" font-size="14" font-weight="600" fill="#f1f5f9">TransitTruth {level}</text>
  <text x="72" y="52" font-family="Arial, sans-serif" font-size="12" fill="#94a3b8">@{username}</text>
  <text x="72" y="68" font-family="Arial, sans-serif" font-size="11" fill="#64748b">{audit_count} audits · {verified_count} verified</text>
</svg>'''
    return svg


def generate_stat_badge(label: str, value: str, color: str = "#2563eb") -> str:
    """Generate a simple stat badge.

    Args:
        label: Badge label
        value: Badge value
        color: Accent color

    Returns:
        SVG string
    """
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="160" height="40" viewBox="0 0 160 40">
  <rect width="160" height="40" rx="6" fill="#1e293b"/>
  <rect width="4" height="40" rx="2" fill="{color}"/>
  <text x="16" y="18" font-family="Arial, sans-serif" font-size="10" fill="#94a3b8">{label}</text>
  <text x="16" y="34" font-family="Arial, sans-serif" font-size="16" font-weight="bold" fill="#f1f5f9">{value}</text>
</svg>'''
    return svg


def generate_profile_readme_section(username: str, audit_count: int,
                                     verified_count: int, relays_audited: int,
                                     avg_score: float) -> str:
    """Generate a complete Profile README section for TransitTruth contributions.

    Args:
        username: GitHub username
        audit_count: Number of audits contributed
        verified_count: Number of verified audits
        relays_audited: Number of unique relays audited
        avg_score: Average audit score

    Returns:
        Markdown string for Profile README
    """
    markdown = f"""## 🛡️ TransitTruth Contributions

[![TransitTruth](https://img.shields.io/badge/TransitTruth-Contributor-2563eb)](https://github.com/dafahaha/transit-truth)

| Metric | Value |
|--------|-------|
| Total Audits | {audit_count} |
| Verified Audits | {verified_count} |
| Relays Audited | {relays_audited} |
| Avg Trust Score | {avg_score:.1f}/100 |

> I contribute to [TransitTruth](https://github.com/dafahaha/transit-truth), an open-source AI API relay audit tool.
> Help make the AI API ecosystem more transparent!
"""
    return markdown


if __name__ == "__main__":
    # Example usage
    badge = generate_contributor_badge("dafahaha", 5, 2)
    print("=== Contributor Badge ===")
    print(badge)

    stat = generate_stat_badge("Audits", "12", "#16a34a")
    print("\n=== Stat Badge ===")
    print(stat)

    readme = generate_profile_readme_section("dafahaha", 5, 2, 1, 56.6)
    print("\n=== Profile README Section ===")
    print(readme)
