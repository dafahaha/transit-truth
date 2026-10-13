# Changelog

All notable changes to TransitTruth will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.4] - 2026-10-14

### Fixed — 覆盖率门 + tokenizer 口径热修（独立审批抓 1 P1 绕过 + 1 P1 引用错误 + 1 P2 口径误报）
- **P1 饥饿绕过 2.0（通用覆盖率门）**：对抗后端只回答 1 个重叠行为探针（n=3、按公开基线 2:1 切分躲过点质量阈值）、其余重叠探针全部 504（n=0）。旧 thin_evidence 门只统计"出现过"的探针，对完全饿死的 n=0 探针不可见 → 实跑 pass/medium、posterior=0.913、无任何标记。修复：覆盖率门改为以**客户端实际发出的探针全集**为分母（`battery.planned_behavioral_ids`），统计每探针可用观测数、行为覆盖率（充分采样的重叠探针 / 应重叠探针）、整体非 200 率。任一应重叠行为探针 n=0，或行为覆盖率 < 0.8，或整体失败率 > 0.5 → 判 `non_cooperation`/证据不足：**不得 pass**（pass 落 `insufficient_evidence`），置信封顶 low，`posterior / likelihood_ratio / posterior_ci_95 / chi2_pvalue` 全部置 `null`。对选择性作答、隔次作恶、部分探针饿死、点质量、伪造 usage 等稀疏形态统一生效；正常充分采样后端不受影响。
- **P2 tokenizer 口径失配**：电池发 `messages=[system, user]`，但 gpt-4o / gpt-4o-mini shipped 基线是 user-only 口径（27/25/29/22/18），真端点按 system+user 自报 43/41/45/38/34 → `tokenizer_consistency` 强制 mismatch → 货真价实的 gpt-4o-mini 被误报 suspicious。修复：用 tiktoken **离线**（仅 token 计数、无需 API key）按电池 system+user 实际请求重算两基线 tokenizer 计数并覆盖 `data/baselines/`（行为 n=50 不动）；`collect_baseline.py` 采集口径改为 system+user 以防再漂移；新增 `tokenizer_caliber` 口径锁定测试（基线均值 == o200k 对电池完整请求的计数，且真实口径下 tokenizer_consistency=match）；e2e/stub 伪造的 user-only 数字改为真实 system+user 值。

### Docs / P1-P3
- **P1 引用事实错误**：UCSB《Your Agent Is Mine》（arXiv:2604.08407）是 **agent 供应链攻击**研究（428 路由中 9 个注入恶意 tool-call、17 个窃取云凭据；"26"系自行加总），**通篇不测模型替换**。已从中转站偷换模型证据中移除，改置于"agent 供应链风险"语境并显式标注不测模型替换；模型替换主张以 CISPA arXiv:2603.01919（"45.83% 的**指纹测试**身份核验失败"，非"45.83% 的中转站"）、Berkeley arXiv:2504.04715、知道创宇 34.9% 为锚点。
- **P2 README 无 Key 快速开始跑不通**：快速开始命令块补设 dummy key（`export TRANSIT_TRUTH_API_KEY=...`，附 PowerShell `$env:` 写法），原样可跑。
- **P3**：`backend/app/__init__.py __version__` 0.1.0 → 0.4.4（全仓版本统一）；删除 CHANGELOG 底部悬空的 v0.2.0 / v0.1.0 release 链接（远端无对应 tag）；README 行为探针数前后统一（8 英文 + 6 中文 = 14）。
- 测试：新增 v0.4.4 回归（单探针 n=3 其余 504 → 非 pass + non_cooperation + 数字 null；全探针各 n=1 → 同样封顶；合作充分采样不受影响；tokenizer 口径锁定）。

## [0.4.3] - 2026-10-14

### Fixed — 饥饿式绕过 / 诚实性热修（独立审批抓 1 P2 安全 + 若干 P2/P3）
- **P2-A 饥饿式行为样本绕过**：对抗后端对每个行为探针只回 1 次公开模态串、其余 2 次回 504，使每探针 n=1。旧 `_behavioral_degeneracy` 跳过 n<2 → 不打回放风险、置信不封顶；单模态样本仍 chi2 匹配点质量基线（p≈0.9985）→ 实跑得到 pass/medium、posterior=0.913、无任何回放警示。修复：(1) 退化检测纳入 n≥1（n=1 恒为点质量，必触发 `deterministic_replay_risk`）；(2) 新增行为样本量下限门——任一重叠探针成功样本 < 3（或整体重叠观测过薄）即标 `thin_evidence`：置信封顶 `low`，并把 `posterior / likelihood_ratio / posterior_ci_95` 一律置 `null`（与 v0.4.2 "无行为证据"诚实契约一致），不再展示伪造的高置信后验。正常充分采样路径（n=3/探针）不受影响。
- **P3 未知模型伪造先验**：无参考基线时 `posterior` 不再打印默认 0.5 / CI=[0,1]，一律 `null`。

### Docs / P2-P3
- **P2-D 夸大文案据实**：`docs/final_release_package.md`、`docs/promotion_guide.md` 约 10 处"80% 以上中转站偷偷降级"无据数字，全部替换为有据口径（UCSB：428 站中 26 家动手脚；CISPA：45.83% 未过行为指纹核验；arXiv:2603.01919）。
- 版本号统一 0.4.3（root + backend `pyproject.toml`、`config.py APP_VERSION`、egg-info 构建产物）。
- 删除 `_redact()` 死代码；reference-server 启动语改为 mode 自适应（消除 "real (stub)" 自相矛盾）；README 说明纯前端 demo 经 esm.sh CDN 加载 js-tiktoken（离线受限）；THIRD_PARTY_NOTICES 点名 USENIX Security'25 LLMmap；去掉过时的"55KB 单文件""46 个单元测试"等静态数字。
- 测试：新增 v0.4.3 回归 3 个（饥饿后端 n=1 必须封顶 low + thin_evidence + 置 null；充分采样对照不受影响；未知模型 posterior 为 null），共 **229 passed / 7 skipped**（只增不减）。

## [0.4.2] - 2026-10-14

### Fixed — 诚实性 / 抗回放热修（独立审批抓到 1 P1 + 1 P2 + 若干 P3）
- **P1 报告数字与 verdict 自相矛盾**：开源目录（无行为参考）下 verdict 已封顶 `insufficient_evidence`，但 JSON 仍打印 `posterior=0.913 / CI=[0.745,0.993] / LR=4.5`——根因是空行为数据 chi2 仍返回哨兵 p=1.0 并被当成"行为强一致 ×3.0"。现在当某探针/整体**无行为重叠样本**（参考行为分布为空或观测为空）时：不 ×3.0、不报暗示高置信的数字，`posterior / likelihood_ratio / posterior_ci_95 / chi2_pvalue` 一律输出 `null`（NA），并给原因 `behavioral_evidence=none`；JSON 与 verdict 自洽。有真实行为基线（gpt-4o-mini）路径的数字不受影响。
- **P2 确定性回放可骗 pass**：行为探针 temperature=0 退化为点质量，公开基线随仓库分发，硬编码约 4 个众数字符串即可确定性拿 pass。现在计算每探针经验熵/众数占比，零熵或点质量（众数占比≈100%）时报告显式标 `statistics.deterministic_replay_risk.flag=true` 并列退化探针；点质量行为证据**不允许无保留高置信 pass**——verdict 可仍为 pass，但 `confidence` 封顶为 `low`。docs/verify.md 与 README 诚实说明：公开探针在 temperature=0 下可被确定性回放，tokenizer 计数是弱信号，官方密码学 attestation 才是终局，本工具是概率性辅助。

### Changed / P3
- `config.py APP_VERSION` 0.3.0 → 0.4.2，与 pyproject 对齐。
- `verify --api-key sk-xxx`（位置/flag 传 key）现在 stderr 告警，推荐环境变量；README 从源码安装段改为 env 写法。
- 整批探针电池新增整体墙钟超时 `--total-timeout`（默认 90s）：挂死/500 后端不再因重试退避拖到 47–137s，到点优雅 fail-closed 返回 `error.code=battery_timeout`。
- 指纹数据集表述统一为原论文 **165 模型**（此前 data/fingerprints/README 与报告文案误写 176）。
- reference-server 无 tokenizer 时降级为显式标注 stub 的提示写入快速开始。
- 竞品表补 truthprobe / BazaarLink Probe / Tosea.ai / token-difr。
- `.pytest_cache/` 不入库（.gitignore 已有，确认未被跟踪）。
- 测试：新增 v0.4.2 回归（零行为证据路径 posterior/LR 为 null；确定性回放后端不得无保留高置信 pass），总数只增不减。

## [0.4.1] - 2026-10-14

### Fixed — 发布阻断热修（独立审批抓到）
- **P0-1 reference-server 422**：`reference_server.py` 把 `FastAPI/Request` 提到模块级 import。此前 `from __future__ import annotations` + 函数体内 import 使 FastAPI 把 `request: Request` 当成必填 query 参数，`/v1/chat/completions` POST 全 422、17/17 探针失败。新增 TestClient 冒烟 + 真实 uvicorn→verify e2e（断言 observations 非空）。
- **P0-2 伪造后端伪 pass（安全红线）**：开源目录 `behavioral:{}` 为空时，卡方哨兵 p=1.0 曾被当成"行为强一致 ×3.0"。现在无行为参考的目录，tokenizer 自报数字（usage.prompt_tokens 由中转站自报、探针数字完全公开）**绝不单独输出 pass**，结论封顶 `insufficient_evidence`。回归测试：上报公开 tokenizer 数字 + 行为乱码的后端必须 NOT pass；对照 gpt-4o-mini（有真实行为基线）同样乱码仍判 suspicious。
- **P1 tokenizer 口径**：指纹重算为 system_prompt+user_prompt 口径（与电池实际发送一致），消除"自己 verify 自己参考后端被判可疑"；`tokenizer_consistency` match 与 mismatch 对称，均要求 overlap≥3。
- endpoint_base_url 剥除 base_url 内嵌 userinfo（凭据不入报告/OTel）；quick mode 不再把 key 当位置 argv（优先 env，位置传 key 告警）。

### Docs
- README 测试数统一（221/7）；补已上线竞品（knowlyr-modelaudit / zing-audit / veridrop / apiranking / IRIS / KBF）；ε-稀释检验降级为辅助工程估算工具；诚实标注指纹库当前为 1 模型 PoC。
- 测试：221 passed / 7 skipped。

## [0.4.0] - 2026-10-14

### Added — 模型真实性核验（stateless verify）
- **无状态核验核心** `app/verify/`：`verify_endpoint(base_url, claimed_model, key from env)` 跑有界探针电池，输出单一机器可读 JSON 报告，三态结论 `pass` / `suspicious` / `insufficient_evidence`。
- **CLI** `transit-truth verify ...`（key 不落盘、不进日志/报告；loopback 需 `--allow-local`，默认 SSRF 防护）。
- **开源参考指纹库** `data/fingerprints/`：Qwen2.5-0.5B 真实 tokenizer 计数；DeepSeek-R1-Distill-Qwen（沿用 Qwen2 tokenizer）；GLM 目录收录（tokenizer 下载受网络限制待补）。
- **自托管参考后端** `transit-truth reference-server --model X`：返回真实 tokenizer prompt_tokens，行为响应为明确标注的桩。
- **ε-稀释序贯检验** `app/verify/sequential.py`：预算内检出假模型的统计能力 / 所需样本。
- **SDK 与可观测**：`from app.verify import verify_endpoint[_sync]`；可选 OpenTelemetry/OpenInference span、DeepEval metric、Langfuse score 示例（`examples/`）。
- **THIRD_PARTY_NOTICES.md**：核验并列出复用/引用的开源资产与许可证。
- 测试：217 passed / 7 skipped。

### Added
- **Statistical analyzer** (`app/core/statistical_analyzer.py`): Rigorous statistical methods for model verification
  - Kolmogorov-Smirnov test for tokenizer distribution comparison
  - Chi-square test for behavioral distribution comparison
  - Bayesian updating with credible intervals
  - False positive/negative rate estimation
  - Default baseline distributions for GPT-4, GPT-3.5, Claude families
- **Continuous monitoring** (`app/core/monitor.py`): Monitor relays at regular intervals
  - 4 alert detection rules (absolute score, score drop, token discrepancy, high latency)
  - 4 alert channels (console, email, Telegram, webhook)
  - History persistence to JSON files
  - Example config at `examples/monitor-config.example.json`
- **One-click contribution** (`app/utils/contributor.py`): Automatically create GitHub Issues
  - Server-side GitHub API integration
  - Token verification
  - Auto-formatted issue body from audit template
  - Anonymous or attributed contribution
- **Standalone frontend** (`standalone/index.html`): Pure frontend version, no backend required
  - All API requests directly from browser
  - Auto-detect base URL from 12 known relays
  - Auto-load model list via `/models` endpoint
  - Quick/deep mode toggle
  - js-tiktoken for client-side token counting
  - Export JSON, copy result, contribute to ranking
- **Initial ranking data** (`data/initial_ranking.json`): 12 audit results for cold start
  - 4 verified entries (official APIs)
  - 2 wolfai.top real audit results
  - 6 community-estimated entries
  - Covers 10 relays and 5 models
- **pyproject.toml**: Full Python package configuration
  - `pip install transit-truth` support
  - `transit-truth` CLI entry point
  - Dependencies: fastapi, uvicorn, httpx, tiktoken, numpy, scipy, rich, click
  - Dev dependencies: pytest, flake8, mypy, ruff
  - Ruff and mypy configuration

### Changed
- **Token "inflation" → "discrepancy"**: Renamed all references to avoid implying fraud
  - Added `chat_template_overhead` field to estimate legitimate token overhead
  - Adjusted suspicious threshold from 15% to 20% (after chat template deduction)
  - Added `discrepancy_note` field with plain-language explanation
  - Updated HTML report, frontend, and CLI displays
- **Capability probes**: Expanded from 4 to 10 probes
  - Added: knowledge cutoff, reasoning chain (bat-and-ball), code bug fix, multilingual, context length, math word problem
  - Added difficulty tiers (easy/medium/hard) and model tier estimation
  - Increased default capability probe count from 4 to 6
- **Probe randomization**: Enhanced anti-detection measures
  - Random probe execution order
  - Random startup delay (0.3-1.5s per probe)
  - Already had randomized probe content

### Improved
- **Anomaly detection**: Expanded from 2 to 5 rules
  - Score deviation >30 from median
  - Token inflation >200% or <0%
  - Latency >30s or <50ms (cached response detection)
  - Duplicate scores appearing 3+ times
  - Exact scores of 0 or 100
- **Contributor reputation system**: Weighted aggregation by contributor trust
  - Reputation score (0-100): audit count 40% + verified count 20% + unique relays 20% - anomaly penalty 20%
  - Reputation levels: Trusted/Established/Regular/New/Unknown
  - Weighted median aggregation (0.5x-1.5x weight based on reputation)
- **Disclaimer**: Expanded from 1 paragraph to 7 detailed points
  - Token discrepancy ≠ fraud
  - Fingerprint confidence <80% is not evidence
  - Ranking data is community-contributed, not independently verified
  - API key never leaves browser (standalone version)
  - Appeal channel via GitHub Issues

## [0.2.0] - 2026-09-12

### Added
- CLI tool with audit/list/export/benchmark commands
- 44 unit tests (now 46)
- Randomized probes for anti-defense
- HTML report generator
- Benchmark data collector
- CI/CD with GitHub Actions
- CONTRIBUTING, CODE_OF_CONDUCT, architecture docs, methodology docs
- 4 issue templates + PR template

### Changed
- Web UI: step-by-step form, auto-detect base URL, model dropdown, quick/deep modes
- Real-time progress bar
- Local audit history (localStorage)
- GitHub Issues as ranking database (0-cost)
- Ranking static page (GitHub Pages compatible)
- Contributor badges (SVG)

## [0.1.0] - 2026-09-10

### Added
- Initial release
- Core audit engine (token verification, model fingerprint, latency/protocol)
- 20 probes (8 tokenizer, 8 behavioral, 4 capability)
- Async HTTP client
- SQLite database
- FastAPI REST API
- Single-page frontend (4 tabs)
- Docker support
- README, LICENSE, .gitignore

[Unreleased]: https://github.com/dafahaha/transit-truth/compare/v0.4.4...HEAD
[0.4.4]: https://github.com/dafahaha/transit-truth/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/dafahaha/transit-truth/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/dafahaha/transit-truth/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/dafahaha/transit-truth/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/dafahaha/transit-truth/releases/tag/v0.4.0
