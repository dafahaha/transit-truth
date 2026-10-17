# 贡献指南 (Contributing to TransitTruth)

感谢你对 TransitTruth 的兴趣！本文档 outlines 如何为项目做贡献。

> **重要**：你不需要有 GitHub 账号，也不需要能访问外网，就可以为项目做贡献！详见下方的[多渠道贡献方式](#多渠道贡献方式)。

---

## 目录

- [多渠道贡献方式](#多渠道贡献方式)
- [分层贡献者体系](#分层贡献者体系)
- [贡献等级制度](#贡献等级制度)
- [国内用户贡献指南](#国内用户贡献指南)
- [开发环境搭建](#开发环境搭建)
- [贡献类型详解](#贡献类型详解)
- [代码规范](#代码规范)
- [PR 流程](#pr-流程)
- [问题反馈](#问题反馈)

---

## 多渠道贡献方式

我们支持 **7 种贡献渠道**，无论你是技术大神还是普通用户，都能找到适合自己的方式：

| 渠道 | 适合人群 | 难度 | 说明 |
|---|---|---|---|
| **GitHub PR** | 技术用户 | ⭐⭐⭐ | 提交代码、文档、基准数据 |
| **GitHub Issue** | 有GitHub账号的用户 | ⭐⭐ | 提交审计结果、报告Bug |
| **本地核验后贡献** | 所有用户 | ⭐ | 本地 `transit-truth serve` 核验后导出/分享结果 |
| **邮件提交** | 所有用户 | ⭐ | 把核验结果JSON发到指定邮箱 |
| **社区提交** | 社区活跃用户 | ⭐ | 在微信群/QQ群/评论区提交 |
| **API 提交** | 高级用户 | ⭐⭐⭐ | 通过REST API批量提交 |
| ~~Gitee~~ | （已失效 404，未提供镜像） | — | 历史镜像已下线，走 GitHub Issue / 邮件 |

### 渠道1：GitHub PR（代码/文档/数据贡献）

```bash
# 1. Fork 仓库
# 2. 克隆你的 fork
git clone https://github.com/your-username/transit-truth.git
cd transit-truth

# 3. 创建功能分支
git checkout -b feature/your-feature

# 4. 做修改
# 5. 运行测试
cd backend && python -m pytest tests/ -v

# 6. 提交并推送
git commit -m "Add your feature"
git push origin feature/your-feature

# 7. 打开 Pull Request
```

### 渠道2：GitHub Issue（审计结果贡献）

1. 打开 [New Issue](https://github.com/dafahaha/transit-truth/issues/new)
2. 选择 "Audit Result Contribution" 模板
3. 填写审计结果信息
4. 提交 Issue

### 渠道3：本地运行后贡献（推荐普通用户）

GitHub Pages 仅是离线演示（内置种子数据，不发送 Key、不直连中转站），不能在线实测。真实模型身份核验请在本地/自托管运行：

```bash
transit-truth serve            # 默认 http://127.0.0.1:8766，浏览器点选
# 或 CLI
transit-truth verify --base-url https://relay.example/v1 --model gpt-4o-mini
```

1. 用本地 `serve`（或 CLI）完成一次核验，得到三态报告
2. 导出结果 JSON，或在报告页点"分享/导出"
3. 通过下方渠道（邮件 / GitHub Issue / 社区）提交结果
4. 填写贡献者信息（可匿名）

> Key 仅存于本次会话内存，不落盘、不进日志、不进可分享报告。

### 渠道4：邮件提交（零门槛）

1. 运行审计，导出结果 JSON
2. 把 JSON 文件作为附件，发送到：`contribute@transit-truth.xxx`
3. 邮件标题格式：`[audit-result] 中转站名称 / 模型名称`
4. 我们会定期审核，批量导入数据库

### 渠道5：社区提交（运营驱动）

- **微信群/QQ群**：在群里发审计结果，管理员定期收集
- **知乎/V2EX评论区**：在相关文章评论区发结果
- **其他社区**：任何你活跃的技术社区

### 渠道6：API 批量提交（高级用户）

```python
import httpx

# 批量提交审计结果
async def batch_contribute(audit_results: list[dict], api_key: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.transit-truth.xxx/v1/contributions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"results": audit_results},
        )
        return response.json()
```

### 渠道7：镜像仓库（当前未维护）

历史上的 Gitee 镜像链接已失效（404），目前未提供国内镜像；请直接通过 GitHub Issue / 邮件 / 社区渠道提交。

---

## 分层贡献者体系

我们把贡献者分为 **5 种类型**，每种类型独立计算等级，避免价值稀释：

| 类型 | 定义 | 贡献方式 | 信誉权重 |
|---|---|---|---|
| **💻 代码贡献者** (Code) | 提交代码、修复Bug、开发新功能 | GitHub PR | ⭐⭐⭐⭐⭐ |
| **📊 基准数据贡献者** (Data) | 提交模型基准数据（50+样本） | GitHub PR / 邮件 | ⭐⭐⭐⭐ |
| **🔍 审计结果贡献者** (Audit) | 提交中转站核验结果 | 本地核验 / 邮件 / 社区 | ⭐⭐⭐ |
| **📝 文档贡献者** (Doc) | 写文档、教程、翻译 | GitHub PR | ⭐⭐⭐⭐ |
| **🌐 社区贡献者** (Community) | 回答问题、组织活动、推广项目 | 社区活动 | ⭐⭐⭐ |

### 为什么要分层？

- **避免价值稀释**：提交一个审计结果就成为"贡献者"，会稀释代码贡献者的价值
- **精准展示**：不同类型的贡献者在不同板块展示，一目了然
- **信誉差异化**：代码贡献者的审计结果信誉权重更高（因为他们更懂技术）
- **激励多元**：鼓励用户在多个方向做贡献，获得多个徽章

### 贡献者展示

在 README 和网站上，贡献者按类型分类展示：

```
## 贡献者

### 🏆 核心贡献者 (Core Contributors)
- @user1 - 代码贡献者 Platinum，项目维护者

### 💻 代码贡献者 (Code Contributors)
- @user3 - Gold (15 PRs merged)

### 📊 数据贡献者 (Data Contributors)
- @user5 - Gold (12个模型基准数据)

### 🔍 审计贡献者 (Audit Contributors)
- 匿名用户 #1234 - Bronze (3次有效审计)
```

---

## 贡献等级制度

每种贡献类型都有 **5 个等级**，独立计算：

| 等级 | 条件 | 徽章 | 信誉乘数 |
|---|---|---|---|
| **Bronze** (青铜) | 首次贡献 | 🟤 | 0.8x |
| **Silver** (白银) | 3次有效贡献 | ⚪ | 1.0x |
| **Gold** (黄金) | 10次有效贡献 | 🟡 | 1.2x |
| **Platinum** (白金) | 30次有效贡献 + 质量审核 | 🔵 | 1.4x |
| **Diamond** (钻石) | 100次有效贡献 + 核心贡献者认可 | 💎 | 1.6x |

### 什么是"有效贡献"？

- **代码贡献**：PR 被合并
- **基准数据**：数据通过质量审核（样本量≥50，采集方法正确）
- **审计结果**：结果通过异常检测（不是明显错误或恶意数据）
- **文档贡献**：PR 被合并
- **社区贡献**：管理员确认

### 特殊徽章

| 徽章 | 获得条件 |
|---|---|
| 👑 核心维护者 | 项目维护团队成员 |
| 🚀 早期贡献者 | 项目发布前30天内贡献 |
| 🌍 多语言贡献者 | 贡献了多语言探针或翻译 |
| 🐛 Bug 猎人 | 报告了3个以上被确认的Bug |

---

## 国内用户贡献指南

### 问题：我没有 GitHub 账号，怎么办？

**答案**：用邮件或社区渠道提交，不需要 GitHub 账号！

1. **本地核验**：`transit-truth serve`（浏览器点选）或 CLI
2. **邮件提交**：把核验结果 JSON 发到 `contribute@transit-truth.xxx`
3. **社区提交**：在微信群/QQ群/知乎评论区发结果

### 问题：我访问 GitHub 不稳定，怎么办？

**答案**：当前未提供国内镜像（历史 Gitee 镜像链接已失效 404）。可直接下载仓库到本地，用 `transit-truth serve` 在本机完成核验，再通过邮件/社区提交结果。

### 问题：我不会用命令行，怎么办？

**答案**：本地运行 `transit-truth serve` 后用浏览器点选即可，无需命令行操作；真正的模型身份核验必须走本地/自托管 serve（浏览器跨域直连受 CORS 限制，Pages 仅为离线演示）。

1. 安装后运行 `transit-truth serve`，浏览器打开 http://127.0.0.1:8766
2. 填写 base_url 与声称模型，可选 API Key
3. 点"开始核验"查看三态结果
4. 导出/分享报告，或通过邮件/社区提交

---

## 开发环境搭建

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 运行测试

```bash
cd backend
# 单元测试（默认）
python -m pytest tests/ -v

# 集成测试（需要设置 API Key 环境变量）
$env:TRANSIT_TRUTH_TEST_API_KEY="sk-xxx"
pytest tests/ -m integration -v
```

### CLI 使用

```bash
cd backend
# 审计
python -m app.cli audit --api-key sk-xxx --base-url https://api.example.com/v1 --model gpt-4o

# 查看历史
python -m app.cli list

# 导出报告
python -m app.cli export --audit-id abc123 --output report.html

# 余额查询
python -m app.cli balance --api-key sk-xxx --base-url https://api.example.com/v1
```

---

## 贡献类型详解

### 1. 添加新探针

探针是 TransitTruth 检测能力的核心。添加新探针：

1. 在 `backend/app/core/probes.py` 中添加探针定义
2. 如果是新类别，添加到对应的探针列表
3. 在 `backend/tests/test_probes.py` 中添加测试
4. 更新方法论文档

**探针设计原则：**
- 保留被测特征，同时随机化具体内容
- 避免中转站可以白名单的固定字符串
- 行为探针使用 temperature=0（确保可复现）
- 能力探针使用 temperature=0（确保答案确定）

### 2. 提交基准数据

基准数据是行为指纹的基础。提交基准数据：

```bash
# 1. 采集基准数据
python collect_baseline.py \
  --model gpt-4o \
  --samples 50 \
  --base-url https://api.openai.com/v1 \
  --api-key sk-your-key \
  --output data/baselines/gpt-4o.json \
  --concurrency 3

# 2. 验证数据质量
python analyze_baseline.py --input data/baselines/gpt-4o.json

# 3. 提交 PR
```

**基准数据质量要求：**
- 样本量 ≥ 50（推荐 200+）
- 使用官方 API（或已验证的中转站）
- 所有探针使用 temperature=0
- 包含完整的元数据（模型版本、采集时间、API端点）

### 3. 提交审计结果

审计结果是排行榜的数据来源。提交审计结果：

1. 用本地 `transit-truth serve`（或 CLI）完成一次核验
2. 导出结果 JSON
3. 通过邮件 / GitHub Issue / 社区渠道提交

**审计结果质量要求：**
- 使用深度模式（10+探针）
- 包含完整的元数据（中转站名称、Base URL、模型、审计时间）
- 不是明显错误或恶意数据

### 4. 改进检测准确率

- 在 `backend/app/config.py` 中添加新模型家族
- 改进 `backend/app/core/fingerprint.py` 中的指纹分析
- 改进 `backend/app/core/auditor.py` 中的评分算法
- 添加新的统计方法到 `backend/app/core/statistical_analyzer.py`

### 5. 修复 Bug

- 查看 [Issue 列表](https://github.com/dafahaha/transit-truth/issues) 中的 Bug
- 编写能复现 Bug 的测试
- 修复 Bug 并确保测试通过
- 提交 PR，清晰描述问题和修复方案

### 6. 改进文档

- 修复错别字，澄清解释
- 添加使用示例
- 改进 README
- 添加架构图
- 翻译文档（中英文）

---

## 代码规范

- **Python**：遵循 PEP 8，最大行长度 120
- **类型提示**：所有函数签名都使用类型提示
- **文档字符串**：所有公共函数和类都写文档字符串
- **函数设计**：保持函数聚焦、单一职责
- **变量命名**：使用有意义的变量名
- **测试**：新功能必须有对应的测试

---

## PR 流程

1. 确保代码通过所有测试（`pytest`，当前 330 passed / 7 skipped）
2. 如有需要，更新文档
3. 完整填写 PR 模板
4. 积极响应 review 反馈
5. 合并前 squash commits（或我们帮你 squash）

---

## 问题反馈

### 报告 Bug

请在 Issue 中包含：

- TransitTruth 版本
- Python 版本
- 操作系统
- 复现步骤
- 预期行为
- 实际行为
- 错误信息或堆栈跟踪

### 功能请求

欢迎功能请求！请打开 Issue，包含：

- 功能的清晰描述
- 为什么有用
- 可能的实现方案（如果你有的话）

---

## 行为准则

请注意，本项目发布了 [贡献者行为准则](CODE_OF_CONDUCT.md)。参与本项目即表示你同意遵守其条款。

---

## 有问题？

随时打开 Issue 或联系维护者。

**感谢你的贡献！🛡️**

---

*本文档持续更新中。如果你有任何建议，欢迎提交 PR 改进本文档！*

