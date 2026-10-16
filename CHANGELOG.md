# Changelog

All notable changes to TransitTruth will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-10-17

### Security — 安全加固（两片全新独立审批：技术片 1 P1 + 3 P2，产品片 5 P2）
- **P1 F1 XSS / HTML 注入**：`webapp/index.html` 的 `renderReport` 原用 `innerHTML` 模板串把服务端返回的 `claimed_model / evidence_reason / error.message / error.code / confidence / matched_reference_model / tokenizer 探针 key-value / behavioral 响应串 / 各 flag.reason / catch 的 err.message` 原样插值（审批用 jsdom 实测 13 个 `onerror` 注入节点进入活 DOM）。修复：新增 `esc()`（转义 `& < > " ' ` $`，连 `$`/反引号一起中和模板插值），所有动态值一律经 `esc()` 后再插值；verdict 用作 CSS class 时只走 `VERDICT_CLASSES` 白名单（pass/suspicious/insufficient_evidence/error），不把原始字符串拼进 class。回归：Python 静态守卫（CI 可跑，页面须含 `esc()`/白名单，renderReport 内服务端字段插值均被 `esc()` 包裹，删 `esc` 即失败）+ 零依赖 Node 本地脚本 `scripts/webapp_esc.test.mjs`（不引入联网硬依赖）。
- **P2 F2 Origin/Host/Content-Type 校验**：`POST /api/verify` 仅接受 `application/json`（允许 `; charset=` 后缀），其余（含跨站免预检的 `text/plain` 简单请求）→ 415 `unsupported_media_type`；带 `Origin` 时 host 必须等于请求 `Host`（同源）否则 403 `cross_origin`；`Sec-Fetch-Site: cross-site` → 403 `cross_site`；回环绑定（`loopback_only=True`，默认）下 Host hostname 必须是回环（localhost/127.x/::1），拒绝任意 Host（防 DNS rebinding 把 attacker.com 指到 127.0.0.1 后读响应）→ 403 `invalid_host`；`--allow-public` 放开 Host 白名单但保留 Origin 同源校验；无 Origin 且无 Sec-Fetch 的 curl/CLI 放行。
- **P2 F3 绑定门控绕过**：原只拒字面 `0.0.0.0`，`192.168.x`/`::`/RFC1918/公网 IP/其它主机名会无 flag 静默启动。改为导出 `is_loopback_host()`（仅 127.0.0.0/8、`::1`、`localhost` 视为回环；去括号 IPv6、去 :port），非回环且无 `--allow-public` → exit 2；`cmd_serve` 据 `--allow-public` 决定 `loopback_only`。
- **P2 F4 Docker 容器内绑定错误**：容器内绑 127.0.0.1 时 docker bridge 只到容器 eth0，宿主 `127.0.0.1:8766:8766` 转发会 ECONNREFUSED。改为容器内 `serve --host 0.0.0.0 --port 8766 --allow-public`（仅私有命名空间内），安全边界在宿主侧 compose 的 `127.0.0.1:8766:8766`（绝不发布 0.0.0.0）；Dockerfile/compose/docs 写清网络命名空间区别，公开 VPS 须 Caddy/TLS。本机未实跑 docker（逻辑修正，环境无 docker）。

### Fixed — 产品片 P2 / 文档诚实性
- **F5 README 叙事矛盾**：旧"零安装在线 Demo / 所有请求直接从浏览器、不需要后端 / Key 不经服务器"与新 CORS 边界冲突。改写为清楚区分：根 `index.html` 的浏览器侧**离线演示/内置演示数据**（无 key、受 CDN 限制）仍然有效；**新的模型身份核验（测中转站真假）必须本地/自托管 `transit-truth serve`**，因为浏览器跨域直连中转端点被 CORS 拦截，在 Pages 填 key 只会得到含糊 `Failed to fetch`。清理重复"零安装/直接浏览器实测"措辞，榜单种子行从 `verified/真实审计/官方API基准` 改为"演示种子（估算，非实测）"。
- **F6 tokenizer 口径改精确**：`tokenizer 匹配但无行为参考` → 仅同族、封顶 `insufficient_evidence`（绝不翻 pass）；`tokenizer 不匹配（错族）` → 记 `mismatch` 并升级 `suspicious`（置空 posterior/LR/CI/卡方以免自相矛盾）。
- **F7 竞品表订正两处误判**：bazaarlink.ai 实为多模型聚合 API 网关/计费路由（非"84 项规则 Probe 检测器"），移出检测器对比表；tosea.ai 实为 PDF/论文转幻灯片生成器（非随机数行为指纹工具），删除该行。
- **2504.04715 措辞**：改为"Berkeley 用 TEE 可信执行环境给出模型完整性密码学证明（形式化/硬件路线，非商业端点实测统计）"，不再表述为"商业现场实测"。

### P3
- 参数钳制：`max_requests` 1–200、`behavioral_samples` 1–20、`timeout` 1–120s、`total_timeout` 1–300s，越界返回干净 400 `invalid_parameter`。
- 并发上限 `asyncio.Semaphore(4)`，超出返回 429 `too_many_requests`，避免本地端口被当代理刷。
- 安全响应头：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`、CSP（`connect-src 'self'`、`frame-ancestors 'none'`，保留内联脚本/样式以免破页）。
- 出站 httpx/httpcore 日志压到 WARNING，确保 access/调试日志不含 key；FastAPI version 改从 `config.APP_VERSION` 读（去掉硬编码 0.5.0）；webapp 统计表补 `ks_pvalue` 行。

### 版本 / 测试
- 版本四源统一 **0.5.1**（root `pyproject.toml`、`backend/pyproject.toml`、`config.APP_VERSION`、`app.__version__`），版本一致性测试断言同步。
- 新增 F1 XSS 静态守卫、F2 四态守卫、F3 `is_loopback_host` 单测+门控、P3 钳制/安全头/并发回归，提交树实测 **292 passed / 7 skipped**（只增不减）。

## [0.5.0] - 2026-10-16

### Added — 本地 Web 工具（`transit-truth serve`，打开网页就能测）
- **本地单页 Web UI**：新增 `backend/app/verify/serve.py`（FastAPI `build_serve_app()`）与受 git 跟踪的自包含静态目录 `webapp/`（不用被忽略的 `web/`）。`POST /api/verify` 在服务端 `await verify_endpoint`，返回脱敏后的三态报告；`GET /api/catalog` 暴露可用参考模型；`GET /` 托管单页 UI（表单 base_url / 声称模型（目录下拉+手填）/ 可选 password Key / 折叠高级采样超时），报告页渲染大号三态横幅、统计（posterior/LR/95%CI/卡方/tokenizer 一致性）、逐探针证据与 `deterministic_replay_risk / thin_evidence / non_cooperation` 标记，并标注"报告不含 key，可安全分享"。
- **CLI `serve` 子命令**：`transit-truth serve [--host 127.0.0.1] [--port 8766] [--allow-public] [--allow-local] [--open]`，默认绑回环，URL 提示走 stderr，`--open` 打开浏览器。

### Security — key 安全红线（回归测试守住）
- **Key 只在内存**：绝不写盘、绝不进日志（含 uvicorn access log）、绝不出现在响应/可分享报告；serve 层 `sanitize_report` 做 defense-in-depth：递归剥除 `api_key/authorization/bearer/key` 等字段并打码 `sk-...`/`Bearer ...`（含嵌在说明串里的形态），且深拷贝不污染输入。
- **同源、无通配 CORS**：UI 与 API 同进程，不发 `Access-Control-Allow-Origin: *`；SSRF 守卫保留（默认拦截回环/内网/元数据，`allow_local` 仅供算子自测，不暴露给请求体）。
- **公共绑定门控**：默认 127.0.0.1；绑 `0.0.0.0` 必须显式 `--allow-public` 并打印醒目风险警告（公开托管=探针代理，勿带真实 key）。
- 测试用标记 key `sk-VERIFY-SECRET-MARKER` 断言它在响应 JSON、静态页、服务端日志均不出现。

### Docs / 部署（诚实边界）
- `docs/serve.md`：本地运行、网络模型、key 安全、为何 Pages 不能直连（CORS）、故障排查；Docker `Dockerfile.serve` + `docker-compose.serve.yml`（仅映射宿主 `127.0.0.1:8766`）、VPS + Caddy/TLS 说明；明确 **Cloudflare Workers/Pages 无法运行 Python 引擎**，静态站点只能做门面，未实现纯 JS 代理即不声称支持。一键脚本 `scripts/serve.sh` / `scripts/serve.ps1`。
- 根 `index.html` Pages 门面升级：首屏"5 秒看懂" + `transit-truth serve` CTA + 工作原理 + 诚实 CORS 边界，保留现有离线 demo，截图/GIF 仅留明确占位。

### 版本 / 测试
- 版本四源统一 **0.5.0**（root `pyproject.toml`、`backend/pyproject.toml`、`config.APP_VERSION`、`app.__version__`），版本一致性测试断言同步。
- 新增 serve 回归 11 个（静态页可达；诚实 pass / 错配非 pass / 无 key insufficient；标记 key 不泄漏到响应/页/日志；非 JSON/缺字段/非对象返回干净 JSON 错误；无通配 CORS；脱敏函数单测；CLI 默认回环与 `--allow-public` 门控），全套 **260 passed / 7 skipped**（只增不减）。

## [0.4.7] - 2026-10-14

### Fixed — v0.4.6 收尾（全新审批：产品片无 P0/P1/P2；技术片无 P0/P1、1 P2 + 2 P3）
- **P2 非 JSON 的 200 响应体拖垮整电池**：上游回 200 但响应体不是合法 JSON 对象（WAF/维护页 HTML、纯文本、空 body、JSON 数组 `[...]`）时，`http_client.py` 的 `response.json()` 抛 `json.JSONDecodeError`（`ValueError` 子类）/`TypeError`，逃逸 `chat_completion` 的重试捕获；经 `battery.py` 无 `return_exceptions` 的 `asyncio.gather` 炸成整体 `transport_error`，其余约 16 条好证据被一并丢弃（fail-closed 但破坏 v0.4.6"单条畸形不炸电池"契约——上一轮只加固了合法 JSON 内的 null content/usage）。双保险修复：① `chat_completion` 在 200 分支把 `json.JSONDecodeError / ValueError / TypeError` 纳入捕获（返回与其它失败一致的失败结果，触发退避重试/记失败，不再冒泡），并显式拒绝 JSON 数组/非对象体（OpenAI schema 要求 `choices`/`usage` 对象）；② `battery.py` 的 `gather` 改 `return_exceptions=True`，单个请求任何异常只降级该探针、不中止整电池。回归测试：17 个请求中 1 个分别返回 HTML / 纯文本 / 空 body / JSON 数组 → 不出现整体 `transport_error`，电池继续完成、该请求计 failures、其余好证据保留，最终出合法三态 JSON，覆盖率/薄证据门正确处置。

### P3
- **P3-1 tokenizer 在贝叶斯不确定带仍升级 pass**：分布回放等情形行为 LR≈0.45（<1）、posterior≈0.51（行为不支持）时，tokenizer match 仍把结论翻成 pass（虽 confidence=low）。修复：tokenizer match 只能在行为证据真正支持（LR≥1 且 posterior≥0.5 支持侧）时维持/升级 pass；当行为 LR<1 / posterior 落在非支持侧时，tokenizer match 不得把结论翻成 pass，落 `insufficient_evidence`（保留 `deterministic_replay`/`thin_evidence` 标记），并附"tokenizer 同族但行为证据不支持"说明。有真实行为基线、行为匹配正常 pass 的路径不受影响。
- **P3-2 文档**：README 竞品表 Ofox 链接 `ofox.run/verify` 已 404，经实测改 `ofox.ai/verify`（200，OfoxAI 官方域）；veridrop 未核实的"约 4.9 万份独立检测报告"删除，仅保留已核实的"约 1.08 万家中转站、付费 PRO 不改检测分"口径。
- 版本号四源统一 **0.4.7**（root `pyproject.toml`、`backend/pyproject.toml`、`config.py APP_VERSION`、`app/__init__.py __version__`）；版本一致性测试断言同步更新。
- 测试：新增 v0.4.7 回归（非 JSON 200 容错 ×4 形态参数化；行为 LR<1 + tokenizer match 不得 pass；正常充分行为匹配 + tokenizer match 仍可 pass），总数只增不减。

## [0.4.6] - 2026-10-14

### Fixed — 契约与健壮性收尾（v0.4.5 全新审批两片均无 P0/P1，3 P2 + 少量 P3）
- **P2 单个畸形字段拖垮整电池**：`battery.py` 对响应字段提取未设防——行为响应 `content:null` 时 `.strip()` 抛 `AttributeError`（不在旧 `(KeyError, IndexError, TypeError)` 捕获内），tokenizer 响应 `usage:null` 时 `None.get(...)` 同样抛错；二者都会使整个电池中止 → `transport_error`，其余约 16 条好证据被一并丢弃（fail-closed 但过脆）。修复：对 `usage`/`message`/`content` 加 `isinstance` 守卫，并把单探针字段提取整段包进 try/except；单条畸形只记为一次失败/缺失（计入 `request_failures`，由既有的覆盖率门 / 薄证据门正确处置），**不再中止整电池**。回归测试：17 个请求中仅 1 个 behavioral repeat 返回 `content:null`（另测 `usage:null`）→ 不得整批 `transport_error`，正常完成、该探针计为缺失、最终出合法三态 JSON。
- **P2 verify stdout 单一 JSON 契约**：verify 的 stdout 被 `Loaded real baseline:` 等诊断日志污染（3 行），破坏"stdout 只有一份机器可读 JSON"契约（jq / `json.load` 直接失败）。修复：基线加载与指纹加载的全部诊断/告警打印（`statistical_analyzer.py`、`reference.py`）一律改走 **stderr**，stdout 仅承载最终 JSON 报告。回归测试：捕获式断言 stdout 不含 `Loaded` 等日志、可解析为单一 JSON，stderr 承载诊断。
- **P2 demo 横幅矛盾**：Pages 离线 demo `index.html` 排行榜横幅"所有数据来自真实审计"与种子行"基于公开信息估算"自相矛盾。修复：横幅改为诚实口径——"离线演示：审计流程为真实实现，榜单与种子数据为基于公开信息估算的演示数据（各行持续标注）"，种子行标注保留。

### P3
- **负 verdict 数字自相矛盾**：tokenizer 失配把 verdict 翻成 `suspicious` 时，行为 `posterior=0.913 / LR=4.5 / CI` 仍展示。修复：该翻转发生时一并把 `posterior / likelihood_ratio / posterior_ci_95 / chi2_pvalue` 置 `null`、置信封顶 `low`，保证报告自洽；补回归测试。
- **竞品表据实**：veridrop"十余万份报告"改为官网当下可核实口径（约 1.08 万家中转站、约 4.9 万份独立检测报告/Claude 分榜）；经公开页核实后补入 TokensQC（tokensqc.com）、Ztest 真测（ztest.ai）、Ofox Model Verify（ofox.run/verify）、大模型照妖镜（llmtest.cn）四家真实存在的同类工具。
- 版本号四源统一 **0.4.6**；`[Unreleased]` 指向 `v0.4.6...HEAD`，补齐 `[0.4.5]` / `[0.4.6]` compare 链接。
- 测试：新增 v0.4.6 回归（单 `content:null`/`usage:null` 不中止电池；诊断日志走 stderr；tokenizer 翻 negative 置空行为数字），总数只增不减。

## [0.4.5] - 2026-10-14

### Fixed — 收尾热修（v0.4.4 全新审批两片均无 P0/P1，4 P2 + 少量 P3）
- **P2 版本号漂移**：`backend/pyproject.toml` 仍钉在 `0.4.3`（其余位置已是 0.4.4），全仓统一 **0.4.5**（root `pyproject.toml`、`backend/pyproject.toml`、`config.py APP_VERSION`、`app/__init__.py __version__`、egg-info 构建产物）。新增**版本一致性测试**（tomllib 解析两份 pyproject + `APP_VERSION` + `__version__` 四源断言同值），防再漂移。
- **P2 tokenizer match 阈值乐观**：重校后 Qwen2.5 与 o200k 在电池 5 探针上 **4/5 相等**（仅 mixed-unicode 差 3 token），旧 0.8 阈值把"声称 gpt-4o-mini、实发 Qwen"判 `match`。修复：满探针覆盖（overlap=5）时 tokenizer 判 `match` 要求 **score=1.0**；0.8 卡线降为 `ambiguous` 并附弱信号 note（tokenizer 仅弱信号、需行为指纹确认）。overlap<3 仍 `insufficient_overlap`、显著分歧仍 `mismatch`；Qwen↔Qwen、gpt↔gpt 自对自仍精确 1.0→match，正常识别不受影响。

### Docs / P3
- **P2 测试数回填**：README 由过时的 229 回填为本次真值（**0.4.4=233**、**0.4.5=238 passed / 7 skipped**）。
- **P2 弱信号说明**：README 原理节与 `docs/verify.md` 明确——重校后不同家族 tokenizer 可能高度趋同（Qwen2.5 vs o200k 5 探针 4 项相等），tokenizer 仅**弱信号**、行为指纹是主判据、官方密码学 attestation 才是终局，不留"强判别家族"暗示。
- **P3**：两个 shipped 指纹 JSON note "Zenodo 176-model" → **165**；知道创宇 34.9% 补口径（849 个"模型×中转站"组合中 296 异常≈34.9%，涉其调查 100 站点中的 75 家），不再粗化为"34.9% 的中转站"；`docs/verify.md` 退出码表补列 insufficient_evidence→0（pass 与 insufficient 均退出 0，suspicious=3，错误=2，以 CLI 实现核实）；删除 `battery.py` 未被消费的死字段 `planned_tokenizer_ids` / `expected_behavioral_repeats`（全仓确认无引用，不留半成品）。
- 测试：新增 v0.4.5 回归 5 个（版本四源一致；o200k 精确观测 match(1.0)；Qwen 数字声称 gpt → ambiguous 非 match + note；Qwen 自对自 match(1.0)；低 overlap/分歧带不受影响），总数只增不减。

## [0.4.4] - 2026-10-14

### Fixed — 覆盖率门 + tokenizer 口径热修（独立审批抓 1 P1 绕过 + 1 P1 引用错误 + 1 P2 口径误报）
- **P1 饥饿绕过 2.0（通用覆盖率门）**：对抗后端只回答 1 个重叠行为探针（n=3、按公开基线 2:1 切分躲过点质量阈值）、其余重叠探针全部 504（n=0）。旧 thin_evidence 门只统计"出现过"的探针，对完全饿死的 n=0 探针不可见 → 实跑 pass/medium、posterior=0.913、无任何标记。修复：覆盖率门改为以**客户端实际发出的探针全集**为分母（`battery.planned_behavioral_ids`），统计每探针可用观测数、行为覆盖率（充分采样的重叠探针 / 应重叠探针）、整体非 200 率。任一应重叠行为探针 n=0，或行为覆盖率 < 0.8，或整体失败率 > 0.5 → 判 `non_cooperation`/证据不足：**不得 pass**（pass 落 `insufficient_evidence`），置信封顶 low，`posterior / likelihood_ratio / posterior_ci_95 / chi2_pvalue` 全部置 `null`。对选择性作答、隔次作恶、部分探针饿死、点质量、伪造 usage 等稀疏形态统一生效；正常充分采样后端不受影响。
- **P2 tokenizer 口径失配**：电池发 `messages=[system, user]`，但 gpt-4o / gpt-4o-mini shipped 基线是 user-only 口径（27/25/29/22/18），真端点按 system+user 自报 43/41/45/38/34 → `tokenizer_consistency` 强制 mismatch → 货真价实的 gpt-4o-mini 被误报 suspicious。修复：用 tiktoken **离线**（仅 token 计数、无需 API key）按电池 system+user 实际请求重算两基线 tokenizer 计数并覆盖 `data/baselines/`（行为 n=50 不动）；`collect_baseline.py` 采集口径改为 system+user 以防再漂移；新增 `tokenizer_caliber` 口径锁定测试（基线均值 == o200k 对电池完整请求的计数，且真实口径下 tokenizer_consistency=match）；e2e/stub 伪造的 user-only 数字改为真实 system+user 值。

### Docs / P1-P3
- **P1 引用事实错误**：UCSB《Your Agent Is Mine》（arXiv:2604.08407）是 **agent 供应链攻击**研究（428 路由中 9 个注入恶意 tool-call、17 个路由触达/试图访问 AWS 金丝雀凭据 canary，未确证凭据泄露；"26"系自行加总），**通篇不测模型替换**。已从中转站偷换模型证据中移除，改置于"agent 供应链风险"语境并显式标注不测模型替换；模型替换主张以 CISPA arXiv:2603.01919（"45.83% 的**指纹测试**身份核验失败"，非"45.83% 的中转站"）、Berkeley arXiv:2504.04715、知道创宇 34.9% 为锚点。
- **P2 README 无 Key 快速开始跑不通**：快速开始命令块补设 dummy key（`export TRANSIT_TRUTH_API_KEY=...`，附 PowerShell `$env:` 写法），原样可跑。
- **P3**：`backend/app/__init__.py __version__` 0.1.0 → 0.4.4（全仓版本统一）；删除 CHANGELOG 底部悬空的 v0.2.0 / v0.1.0 release 链接（远端无对应 tag）；README 行为探针数前后统一（8 英文 + 6 中文 = 14）。
- 测试：新增 v0.4.4 回归（单探针 n=3 其余 504 → 非 pass + non_cooperation + 数字 null；全探针各 n=1 → 同样封顶；合作充分采样不受影响；tokenizer 口径锁定），合计 **233 passed / 7 skipped**（只增不减）。

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

[Unreleased]: https://github.com/dafahaha/transit-truth/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/dafahaha/transit-truth/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/dafahaha/transit-truth/compare/v0.4.7...v0.5.0
[0.4.7]: https://github.com/dafahaha/transit-truth/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/dafahaha/transit-truth/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/dafahaha/transit-truth/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/dafahaha/transit-truth/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/dafahaha/transit-truth/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/dafahaha/transit-truth/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/dafahaha/transit-truth/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/dafahaha/transit-truth/releases/tag/v0.4.0
