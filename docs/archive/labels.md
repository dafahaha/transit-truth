# GitHub Labels 设计

排行榜和项目管理使用的 Labels 体系。

## 审计结果 Labels

| Label | 颜色 | 用途 |
|---|---|---|
| `audit-result` | #0E8A16 (绿色) | 审计结果提交，排行榜数据源 |
| `relay:wolfai.top` | #1D76DB (蓝色) | 按中转站筛选 |
| `model:gpt-4o` | #5319E7 (紫色) | 按模型筛选 |
| `trust:high` | #0E8A16 (绿色) | 高信任度 (≥80分) |
| `trust:medium` | #D4C5F9 (浅紫) | 中等信任 (60-79分) |
| `trust:low` | #FBCA04 (黄色) | 低信任 (40-59分) |
| `trust:critical` | #B60205 (红色) | 危险 (<40分) |
| `verified` | #0E8A16 (深绿) | 经过多次验证 (≥3次相同结果) |
| `preliminary` | #FEF2C0 (浅黄) | 初步数据 (<3次验证) |
| `needs-review` | #E4E669 (亮黄) | 需要人工审核 (异常值/格式问题) |

## 项目管理 Labels

| Label | 颜色 | 用途 |
|---|---|---|
| `bug` | #D73A4A (红色) | Bug 报告 |
| `enhancement` | #A2EEEF (浅蓝) | 功能增强 |
| `documentation` | #0075CA (蓝色) | 文档改进 |
| `good first issue` | #7057FF (紫色) | 适合新手的任务 |
| `help wanted` | #008672 (青绿) | 需要帮助 |
| `probe` | #FBF0DE (浅橙) | 新探针/检测方法 |
| `research` | #D4C5F9 (浅紫) | 研究相关 |

## 自动标签规则

GitHub Actions 会根据 Issue 内容自动添加以下标签：

1. **`audit-result`**: 使用审计结果模板创建的 Issue
2. **`relay:*`**: 从 Issue body 的 `relay:` 字段提取
3. **`model:*`**: 从 Issue body 的 `model:` 字段提取
4. **`trust:*`**: 从 Issue body 的 `trust_level:` 字段提取
5. **`verified` / `preliminary`**: 根据同一中转站+模型的审计次数自动判断
6. **`needs-review`**: Token膨胀率>200%或<0%，或格式不正确

## 创建 Labels 的脚本

```bash
# 使用 GitHub CLI 创建 labels
gh label create audit-result --color "0E8A16" --description "审计结果提交"
gh label create verified --color "0E8A16" --description "经过多次验证"
gh label create preliminary --color "FEF2C0" --description "初步数据"
gh label create needs-review --color "E4E669" --description "需要人工审核"
gh label create trust:high --color "0E8A16" --description "高信任度"
gh label create trust:medium --color "D4C5F9" --description "中等信任"
gh label create trust:low --color "FBCA04" --description "低信任"
gh label create trust:critical --color "B60205" --description "危险"
```
