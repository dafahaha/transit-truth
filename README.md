# TransitTruth 🛡️

[English](README.en.md) · 中文

![TransitTruth Banner](docs/banner_1280x640.png)

> **AI API 模型真实性核验 / 路由层可信度监控** — 无状态验证你用的模型是否货真价实。

---

## 🚦 模型真实性核验（`transit-truth verify`）

新增的核心产品能力：给一个 OpenAI 兼容端点和它**声称**的模型名，跑一个**有界**探针电池，对比本地参考指纹，输出**单一机器可读 JSON 报告**与三态结论。

```bash
# key 从环境变量读，不落盘、不进日志/报告
export TRANSIT_TRUTH_API_KEY=sk-...
transit-truth verify --base-url https://your-relay.com/v1 --model gpt-4o-mini
```

报告样例：

```json
{
  "claimed_model": "gpt-4o-mini",
  "verdict": "pass",
  "confidence": "medium",
  "statistics": {
    "matched_reference_model": "gpt-4o-mini",
    "posterior": 0.87,
    "tokenizer_consistency": {"score": 1.0, "verdict": "match"}
  },
  "disclaimer": "Probabilistic auxiliary evidence, NOT a cryptographic proof."
}
```

三态结论：`pass` / `suspicious` / `insufficient_evidence`（证据不足时**绝不硬判**）。

### 🖥️ 本地 Web UI（`transit-truth serve`）

不想敲命令？本地起一个网页，填地址/模型/可选 Key，浏览器里直接出三态报告：

```bash
transit-truth serve            # 默认 http://127.0.0.1:8766，加 --open 自动开浏览器
```

- Key 仅本次会话内存使用：**不落盘、不进日志、不进可分享报告**；默认只绑 `127.0.0.1`，绑定 `0.0.0.0` 需显式 `--allow-public`。
- 浏览器受 CORS 限制无法直连中转端点，真实测试由本地服务端发探针；静态 GitHub Pages 只能做门面，不能在线实测。部署（Docker / VPS + Caddy / Cloudflare 边界）见 [docs/serve.md](docs/serve.md)。

**无付费 Key 的自托管参考后端**（用真实 tokenizer 生成参考指纹）。verify 客户端**强制要求一个非空 API key**（本地 reference-server 本身不校验它），所以先设一个 dummy 值：

```bash
# bash / macOS / Linux
export TRANSIT_TRUTH_API_KEY=local-dummy-no-billing
# Windows PowerShell: $env:TRANSIT_TRUTH_API_KEY="local-dummy-no-billing"

transit-truth reference-server --model qwen2.5-0.5b-instruct --port 8765
transit-truth verify --base-url http://127.0.0.1:8765/v1 \
    --model qwen2.5-0.5b-instruct --allow-local
```

> **无 tokenizers 时降级为 stub**：需要真实 tokenizer 计数时先 `pip install "transit-truth[reference]"`（装 `tokenizers` 包）；reference-server 启动时若下载不到真实 tokenizer（网络受限，`HF_ENDPOINT` 默认 `https://hf-mirror.com`），会自动降级为**显式标注的 plumbing stub** 模式——`prompt_tokens` 只是哈希占位值、行为内容是 `stub-*` 固定串，服务启动 stderr 与 `GET /v1/models` 的 `mode`/`note` 会明确告诉你是 stub，**不会假装是真模型**。此时 verify 只能跑通管线，无法给出任何认证。
>
> **覆盖范围（诚实标注）**：当前自带参考指纹仅覆盖本地开源模型——Qwen2.5-0.5B（真实 tokenizer 计数）、DeepSeek-R1-Distill-Qwen（沿用 Qwen2 tokenizer）、GLM（目录已收录，tokenizer 下载受网络限制待补）。**GPT/Claude/Gemini 等闭源指纹需用户提供自己的 key 后采集接入。**
>
> **定位声明**：黑盒结果是**概率性辅助证据，不是密码学证明，也不做真伪裁判**。`suspicious` 不等于"确定造假"。行为探针在 temperature=0 下退化为点质量，公开基线可被确定性回放（硬编码约 4 个众数字符串即可复现"匹配"），报告对此会显式标 `deterministic_replay_risk` 并把置信封顶——**官方密码学 attestation 才是终局，本工具只是概率性辅助**。详见 [docs/verify.md](docs/verify.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

Python SDK：`from app.verify import verify_endpoint`（可选 OpenTelemetry/OpenInference、DeepEval、Langfuse 集成见 `examples/`）。

下面保留的原有能力（行为指纹动物探针、Token 计费审计、社区排行榜、持续监控）均为**子模块**，见目录与下文各节。

---

## 🔥 我们发现了什么？

我们用27分钟、2600次API请求，发现了GPT模型的"行为指纹"：

| 探针 | gpt-4o-mini | gpt-4o | 正常随机 |
|---|---|---|---|
| 选1-10的数字 | **7（100%）** | 7（98%） | 每个数字10% |
| 掷骰子 | **4（96%）** | 4（56%） | 每个数字16.7% |
| 选随机动物 | Dolphin（16%） | **Okapi（76%!）** | 均匀分布 |
| 选随机字母 | **G/M（并列 40%）** | **K（44%）** | 每个字母3.8% |
| 选颜色 | Cerulean（74%） | Cerulean（92%） | 均匀分布 |

**关键发现：**
- gpt-4o-mini选1-10的数字，**100%返回7**（零方差！）
- gpt-4o选随机动物，**76%返回Okapi**（㺢㹢狓，罕见非洲长颈鹿近亲）
- 用"响应是否为 Okapi"这条简单规则，在**同一基准样本上**做重代入（resubstitution）得到 **88% 准确率**（Wilson 95%CI [0.80, 0.93]，bootstrap [0.81, 0.94]）。注意：动物探针的 TVD=0.90 是**分布距离**，不是分类准确率；这是 in-distribution 自洽检验，不是独立 held-out 准确率。

> **效度说明（务必先读）**：上述基准均通过**单个 OpenAI 兼容中转站（wolfai.top）**采集，**不是官方端点**。我们只声称"在该中转站，两个标称端点呈现可区分的行为画像"，不声称是与厂商无关的模型指纹；基准本身也继承了中转站实际提供的模型。官方金标准基线需要官方 API 访问，属未来工作。

这些"行为指纹"是训练数据和 RLHF 的产物；要在真实流量上伪造它，中转站需要实际返回真模型、后处理输出分布，或微调一个替身模型——成本不低，但并非"不可能"。

---

## 这是什么？

TransitTruth 是一个开源的 **AI API 安全审计平台**，基于学术前沿的行为指纹技术（参考 [One Token Is Enough, arXiv:2607.10252](https://arxiv.org/abs/2607.10252)），帮助用户验证：

- **🔍 模型身份验证**：你付了GPT-4o的钱，实际用的是GPT-4o还是GPT-4o-mini？还是GPT-3.5？
- **💰 Token计费审计**：实际用1000 token，中转站收你1500 token的钱？
- **⚡ 性能监控**：延迟、可用性、错误率是否符合承诺？
- **📋 协议合规**：响应格式是否符合OpenAI API规范？
- **🏆 社区排行榜**：全民共建的中转站信誉排行榜

## 为什么需要这个？

通过中转站（relay）使用 LLM API 时，用户无法在技术上确认"应答的模型就是付费的那个"。由于大模型单价更高，中转站有经济动机用更小/更便宜的模型顶替旗舰模型，同时按旗舰计费。学术界已从工程与硬件路径提出对策：[arXiv:2504.04715](https://arxiv.org/abs/2504.04715)（Berkeley）主张用 **TEE（可信执行环境）**给出模型完整性的密码学证明（形式化/硬件路线，非商业端点实测统计），作为"官方 attestation 终局"的一类方案；本仓库则走轻量黑盒概率辅助路线。Token 计数虚高、费率不透明等问题也让自验证变得有必要。

但普通用户没有工具能核查自己用的中转站是否"参水分"。TransitTruth 就是为了给用户一个低成本、可复现的核查手段。

## 检测原理

### 1. 🧬 行为指纹（核心技术）

不同模型在"随机"任务上有强烈的分布偏好——这是训练数据和 RLHF 的产物。我们用 8 个英文行为探针（随机数 1-100、随机数 1-10、字母、颜色、抛硬币、掷骰子、动物、星期；另有 6 个中文文化探针，合计 14 个），每个采样 50 次，构建经验分布，再用**卡方检验 + KS 检验 + 贝叶斯更新**对比基准分布，计算模型匹配的后验概率。

> 响应做了归一化（如 "Heads." 与 "Heads" 合并、大小写统一）。

> **探针口径交叉标注（v0.4.7）**：旧分析子模块的探针目录含 14 个行为探针（8 英文 + 6 中文）；自托管 `verify` 电池只与"已采集参考"的探针重叠比对，shipped gpt-4o-mini 参考覆盖 **5 tokenizer + 8 behavioral**（其中多数为可确定性回放的模态/点质量探针），6 个中文行为探针尚无参考分布；10 个能力探针仅作辅助、不参与 pass/suspicious/insufficient 三态判定。默认电池 = 5 tokenizer + 4 behavioral×3 repeats = 17 请求。

**实测效果（同一中转站两个标称端点）：**
- gpt-4o-mini vs gpt-4o：**5/8 探针**统计显著差异（p<0.05；抛硬币探针在归一化后 TVD=0.08、未校正 Pearson 卡方 p=0.092，不再显著；经 Yates 连续性校正后 p≈0.206，两种口径下硬币均不显著，5/8 结论稳健）
- 最强区分探针（选动物）：TVD=0.90；"是否为 Okapi"规则的重代入准确率 **88%**（Wilson [0.80,0.93]）。TVD 是分布距离，不等于准确率。
- 整体管线：后验概率 **0.913**，95% 可信区间 [0.885, 0.937]。这是**基线样本对自身参考的 in-distribution resubstitution（自洽性检验）**，用于验证管线内部一致；**不是**独立数据上的 held-out 检测准确率。

### 2. 🔤 Tokenizer指纹

不同模型家族历史上使用不同的tokenizer（GPT用cl100k/o200k，Claude用自定义tokenizer，Gemini用SentencePiece）。发送精心构造的字符串（数字序列、CJK、emoji、代码、URL），对比token计数，可作为后端模型家族的**辅助线索**。

**弱信号，不可反推家族（v0.4.5 重校后诚实口径）**：重校基线后发现，不同家族的 tokenizer 在公开探针上可能高度趋同——Qwen2.5 的 tokenizer 与 o200k（gpt-4o）在电池 5 个探针中 **4 项完全相等**（仅 mixed-unicode 差 3 token）。因此 tokenizer 计数只是**弱信号**：满探针覆盖下 4/5 一致已判 `ambiguous` 而非 `match`，**不能据此反推模型家族**；行为指纹才是主判据，官方密码学 attestation（厂商签名响应）是唯一终局，本工具只是概率性辅助证据。

**局限**：不能区分同一家族的不同模型（如gpt-4o vs gpt-4o-mini）——这正是行为指纹的价值。

### 3. 🧠 能力测试

简单推理题、代码生成题、指令跟随测试、多语言翻译，区分高/中/低等级模型。

### 4. 💰 Token计数对比

将中转站返回的token计数与本地tiktoken精确计算对比，检测是否存在计费膨胀。同时估算chat template overhead，避免误判。

### 5. ⚡ 延迟与协议检查

测量延迟分布（P50/P95/P99）、错误率，验证响应结构、错误格式、响应头是否符合OpenAI API规范。

## 快速开始

### 🎬 离线演示（根 index.html，无需 Key）

打开根目录 [index.html](index.html)（GitHub Pages: https://dafahaha.github.io/transit-truth/）可以**先看演示**：一键体验完整审计流程，看到"声称 gpt-4o 实际降级"的典型场景。这是**离线/内置演示数据**，不连接任何真实中转站。

> 注：根 `index.html` 在浏览器端用 `js-tiktoken` 做 token 计数，该运行时经 **esm.sh CDN**（`https://esm.sh/js-tiktoken`）加载。因此纯前端演示在**离线 / 无公网**环境下受限——离线时只能看内置演示数据。演示（无需 Key）部分不依赖该 CDN。

### 🖥️ 真实模型身份核验（必须本地/自托管 `transit-truth serve`）

**注意：本 Pages 静态页不能直接测真实中转站。** 浏览器受 **CORS** 限制无法跨域直连第三方中转端点，在网页里填自己的 key 直接请求只会得到含糊的 `Failed to fetch`，且浏览器也不应把 key 交给目标域。要真实验证"声称的模型是不是货真价实"，请在本机或 VPS 跑本地服务（服务端发探针，页面只做表单+渲染）：

```bash
transit-truth serve            # 默认 http://127.0.0.1:8766，加 --open 自动开浏览器
```

Key 仅本次会话内存使用，不落盘/不进日志/不进分享报告；详见 [docs/serve.md](docs/serve.md)。

> 注：`standalone/index.html` 现为跳转到根 `index.html` 的重定向页。

### 🐳 使用Docker

```bash
docker-compose up -d
```

然后访问 http://localhost:8000

> 部署注意：compose 已显式 `user: "1000:1000"`（与 Dockerfile 内 `appuser` 对齐）。`./data` 挂载到容器 `/app/data` 后，该目录属主由**宿主目录**决定；若宿主 `./data` 对 UID 1000 不可写，请先在宿主 `sudo chown -R 1000:1000 ./data`，否则首次写 SQLite 会因 EACCES 返回 500。

> 反向代理与限流：限流默认按 **TCP 对端 IP** 分桶，因此直连部署最安全（调用方无法伪造 `X-Forwarded-For` 换配额桶）。若必须把本服务放在 nginx / 云 LB 之后，请设置环境变量 `TRUSTED_PROXIES=<代理IP,逗号分隔>`，例如 `TRUSTED_PROXIES=10.0.0.1,10.0.0.2`。只有当请求的 TCP 对端落在可信代理列表内时，服务才会解析 `X-Forwarded-For`（从右向左跳过可信代理后取第一个不可信跳作为真实客户端 IP）；未配置时即使客户端带了 `X-Forwarded-For` 也会被忽略。请勿把公网客户端 IP 加入 `TRUSTED_PROXIES`。
>
> 两个部署前提：① 上述右向左解析**依赖每个可信代理在 `X-Forwarded-For` 右侧追加自身地址**——nginx 请用 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`，切勿用 `$http_x_forwarded_for` 原样透传（否则客户端在左侧伪造的 IP 会被当成真实客户端）。② 限流计数器是**进程内**状态，`uvicorn --workers N>1` 时各 worker 独立计数，实际配额约为单 worker 的 N 倍；需要严格全局配额请前置统一网关或改用外部存储限流。
>
> 审核与内存快照：`python -m app.moderation approve` 会把 `contributions.status='approved'` 落库并原子写入排行榜行，但**正在运行的 web worker** 里那个信誉系统实例是启动时从 DB 载入的内存快照，不会自动感知这次 approve——其 `get_contributor_stats` / `get_top_contributors` 的 `valid_contributions` 计数会保持陈旧，直到 worker 重启。如需立即反映到前端贡献者计数，请在 CLI approve 后滚动重启 web worker（systemd `restart=always` 或 k8s rolling restart 均可）；排行榜数据本身读 DB，不受此影响。

### 💻 本地运行

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

然后访问 http://localhost:8000

### 📦 从源码安装（CLI）

<!-- PYPI-FLIP：发布到 PyPI 后，把下面整段替换为 `pip install transit-truth`
     （真实 tokenizer 用 `pip install "transit-truth[reference]"`），并删除
     "PyPI 上没有"这句话；具体清单见 docs/PUBLISHING.md 的 post-publish checklist。 -->
PyPI 上**尚未发布** `transit-truth` 包，当前请从源码安装：

```bash
git clone https://github.com/dafahaha/transit-truth.git
cd transit-truth
pip install -e .

# key 从环境变量读（位置传 sk-xxx / --api-key sk-xxx 会在进程列表可见，仅兼容告警）
export TRANSIT_TRUTH_API_KEY=sk-your-key
transit-truth verify --base-url https://your-relay.com/v1 --model gpt-4o
```

（后端方式见上方"本地运行"：`cd backend; pip install -r requirements.txt`。）

## 使用方法

1. 打开Web界面或在线Demo
2. 输入中转站的API Key、Base URL、模型名称
3. （可选）输入官方API Key用于精确对比
4. 选择检测模式：快速（3探针，~10秒）/ 深度（10探针，~60秒）
5. 点击"开始审计"
6. 查看审计结果、行为指纹分布图、详细报告
7. （可选）提交审计结果到社区贡献队列（进入人工审核，审核通过后才计入排行榜）

## 功能特性

### ✅ 已实现
- [x] **行为指纹验证**（14个行为探针：8英文+6中文，卡方检验+KS检验+贝叶斯更新）
- [x] **Tokenizer指纹**（8个tokenizer探针）
- [x] **能力测试**（10个能力探针，模型等级估算）
- [x] **Token计费审计**（tiktoken精确计算，差异率检测）
- [x] **延迟与协议检查**（P50/P95/P99，7项协议合规）
- [x] **余额查询**（多中转站账户余额聚合，低余额自动告警）
- [x] **统计不确定性量化**（Wilson置信区间+样本量评估+95%可信区间）
- [x] **生产级弹性机制**（指数退避重试+限流检测+断路器模式+详细日志）
- [x] **模型参考数据**（14个模型的公开数据：价格/ELO/智能指数/延迟）
- [x] **Web UI**（4个Tab，步骤式表单，进度条，苹果风格设计）
- [x] **浏览器离线演示**（零安装，内置演示数据，非真实端点实测）
- [x] **CLI工具**（一行命令审计+余额查询）
- [x] **HTML报告生成**（可分享的审计报告）
- [x] **审计结果分享卡片**（1200x630 PNG，一键下载分享社交媒体）
- [x] **社区排行榜**（全民共建，贡献者信誉系统）
- [x] **持续监控+告警**（4种告警检测，4种告警通道）
- [x] **真实基准数据库**（gpt-4o-mini、gpt-4o，各50样本）
- [x] **灵活配置管理**（14个环境变量，支持自定义探针数量/超时/重试等）
- [x] **测试**：实测 **300 passed / 7 skipped**（v1–v5 累计新增无状态核验、指纹库、序贯检验、加固与集成测试；v0.4.2 诚实性/抗回放、v0.4.3 饥饿式样本绕过回归、v0.4.4 覆盖率门+tokenizer 口径、v0.4.5 版本一致性+tokenizer 严格匹配回归、v0.4.6 单字段容错+stdout 单一 JSON 契约+负 verdict 自洽回归、v0.4.7 非 JSON 200 响应体容错+tokenizer 不确定带不升级 pass 回归、v0.5.0 本地 Web serve 端点+key 不落盘/不进日志/脱敏+公共绑定门控回归、v0.5.1 serve XSS 转义+Origin/Host/Content-Type 守卫+绑定门控+Docker 修正回归、v0.5.2 wheel 打包 webapp+全局 Host/Origin 守卫+NaN/Infinity 拒绝+上游错误体不泄漏 key 回归）；其中端到端桩测试离线可跑，真实 API key 集成测试用 `pytest -m integration` 单独运行
- [x] **CI/CD**（GitHub Actions，Python 3.10/3.11/3.12矩阵）

### 🚧 开发中
- [ ] 更多模型基准数据（Claude、Gemini、Llama、Qwen）
- [ ] 增加基准样本量到200+（当前50样本，统计误差约±14%）
- [ ] 浏览器插件（实时审计正在使用的API）
- [ ] 移动端适配

## 学术背景

本项目基于以下学术研究：

- **[One Token Is Enough](https://arxiv.org/abs/2607.10252)** (arXiv:2607.10252, 2026) — 单token输出分布的模型指纹方法，165个模型验证，EER 7.3%
- **[CoIn](https://arxiv.org/abs/2505.13778)** (arXiv:2505.13778, 2025) — 隐藏推理token计数审计框架，检测token数膨胀（94.7%成功率）
- **[RAFP](https://arxiv.org/abs/2505.12682)** (arXiv:2505.12682, 2025) — Rare-region 指纹，识别 LLM 谱系，对微调/量化稳健
- **[Model Provenance Testing](https://arxiv.org/abs/2502.00706)** (arXiv:2502.00706, 2025) — 黑盒模型来源测试

我们的工作定位：
1. **同家族细粒度区分**：在两个标称同家族端点（gpt-4o vs gpt-4o-mini）上展示行为画像可被区分（最强 TVD=0.90）；这是 tokenizer 指纹做不到的。我们**不**声称这是"首个"此类研究，也不声称已在独立 held-out 数据上验证泛化。
2. **工程化全功能平台**：不只是指纹工具，而是完整的API安全审计平台
3. **中文社区优先**：面向中文用户，解决国内中转站乱象
4. **零门槛离线演示**：根 index.html 浏览器即用（内置演示数据；真实模型身份核验走本地 `transit-truth serve`）

### 相关工作与已上线竞品（诚实对标）

本赛道已相当拥挤，我们**不**是首个做中转站审计的工具。已上线的同类项目：

| 项目 | 状态 | 与本项目重叠 |
|---|---|---|
| **knowlyr-modelaudit**（PyPI，MIT） | 已上线 CLI+MCP，行为指纹+蒸馏检测 | 与 `verify` SDK/CLI 几乎同定位 |
| **zing-audit**（PyPI） | local-first CLI，审计偷换/截断上下文/假流式/计费虚高 | 与 CLI 直接同赛道 |
| **veridrop.org**（开源） | 官网当下口径：已覆盖约 1.08 万家中转站、付费 PRO 套餐不改检测分，贝叶斯加权红黑榜 | 与"排行榜/买徽章"方向**直接撞车且已规模化**——该身位已被占据 |
| **apiranking.com** | 自研探针周期性轮询，模型真假+费用实测 | 同上 |
| **IRIS**（arXiv:2607.20860） | 预算化黑盒审计模型替换与路由稀释，并估计稀释比例 ε̂ | 已覆盖本仓库"ε-稀释预算化检验"的核心思想 |
| **KBF**（arXiv:2605.29524） | 知识边界指纹，可检出 5~10% 流量掺假 | 覆盖 ε-稀释场景 |
| **truthprobe**（GitHub+PyPI） | 已上线 LLM 审计 CLI | 与 `verify` 同定位 |
| **token-difr**（PyPI） | 用参考 provider 返回的 token log-prob 比对生成序列是否一致 | log-prob 路线，需参考 provider 返回 logprobs，与自报 token 计数是不同信号 |
| **TokensQC**（tokensqc.com） | 免费在线 AI API 质检：协议一致性 / 模型身份 / 延迟探针 | 同定位在线工具 |
| **Ztest 真测**（ztest.ai） | 独立第三方中转站模型真伪检测 + 可信度排行 | 与"红黑榜"方向直接撞车 |
| **Ofox Model Verify**（ofox.ai/verify） | AI 网关自带免费"模型验真"：身份 + 拒答指纹探针 | 同定位在线工具 |
| **大模型照妖镜**（llmtest.cn） | 纯前端（基于 GitHub 开源项目），多维度检测套壳 | 同定位在线工具 |

> **勘误（v0.5.1）**：早先表中误把 bazaarlink.ai 列为"84 项规则 Probe 检测器"、把 tosea.ai 列为"随机数行为指纹工具"。经复核：**BazaarLink（bazaarlink.ai）实为多模型聚合 API 网关/计费路由**（OpenAI/Anthropic/Google 等单 endpoint 聚合），并非模型真伪检测器，故移出检测器对比表；**Tosea.ai 实为 PDF/论文转幻灯片的生成工具**，与 LLM 身份核验无关，已删除该行。

我们的真实身位（二次工程集成，**非方法论创新**）：
- **三态 fail-closed JSON 报告契约**（`pass / suspicious / insufficient_evidence`，证据不足绝不硬判）；
- **自托管 / 可嵌入**（无 SaaS、无排行榜）：`verify` SDK 与 `reference-server` 可嵌入 Agent/网关做准入，与 zing-audit 错位竞争；
- **中文开源模型 tokenizer 目录**——但需诚实说明其**当前规模是 1 个模型的 PoC**（见下）。

> **关于"预算化 ε-稀释检验"**：`backend/app/verify/sequential.py` 的样本量/检出力计算是闭式工程估算工具，用于回答"给定预算 N 与稀释 ε，能否检出掺假"。方法层面 IRIS（arXiv:2607.20860）已做过预算化审计与 ε 估计，我们此处只是一个实用辅助计算器，**不声称方法论原创**。
>
> **指纹库覆盖现状（诚实标注）**：`data/fingerprints/` 当前仅 **Qwen2.5-0.5B-Instruct 一个模型的真实 tokenizer 计数 PoC**（7 个探针，无行为分布）；GLM tokenizer 因镜像限流 pending；DeepSeek-R1-Distill-Qwen 派生自 Qwen2 tokenizer（计数相同，tokenizer 无法区分两者）。GPT/Claude/Gemini 闭源指纹需用户自配 key 采集。tokenizer 信号分两种情形：① **tokenizer 匹配但无行为参考**——只能说明同族，**不得输出 `pass`**，结论封顶 `insufficient_evidence`；② **tokenizer 不匹配（错族）**——会计 `mismatch` 并升级为 `suspicious`（覆盖行为统计结果，同时置空 posterior/LR/CI/卡方以免自相矛盾）。

## 真实基准数据

我们开源了真实采集的模型基准数据（经同一 OpenAI 兼容中转站 wolfai.top 采集，非官方端点）：

| 模型 | 样本数 | 探针数 | 总请求 | 采集时间 | 文件 |
|---|---|---|---|---|---|
| gpt-4o-mini | 50 | 26 | 1300 | 15 分钟 | `data/baselines/gpt-4o-mini.json` |
| gpt-4o | 50 | 26 | 1300 | 12 分钟 | `data/baselines/gpt-4o.json` |

> **开发期样本说明**：`data/baselines/dev_samples/` 下的 `gpt-4o-mini-test.json`、`gpt-4o-mini-concurrent-test.json` 是早期 3→5→50 采样的开发期增量样本，已移出正式基线目录。`load_real_baselines` 仅加载上表两个正式文件（子目录内文件不参与 glob，且文件名含 "test" 显式跳过），这些样本不进入任何分析。

> **数据缺口披露（gpt-4o-mini）**：mini 的 tokenizer 探针未全部拿到可用样本——`tok-digits`、`tok-cjk`、`tok-emoji` 三个探针零可用响应（冷启动限流），`tok-whitespace` 仅 37/50 条可用；实际拿到可用样本的 tokenizer 探针为 5/8（4 个 n=50、1 个 n=37）。上表"26 探针 / 1300 请求"为设计口径（gpt-4o 侧为完整 26/1300）。所有头条行为指纹结论（Okapi、TVD=0.90、后验 0.913 等）均来自 8 个 n=50 齐全的 behavioral 探针，不受此缺口影响。

数据采集脚本：`collect_baseline.py`（支持并发，用任何 OpenAI 兼容 API 即可）；分布/TVD/卡方/分类器表格由 `docs/generate_tables.py` 从 JSON 自动生成。

## 学术产出（Tech Report）

本项目的实验方法、数据与结论整理为**扩展技术报告（extended technical report）**（含完整方法论/公式推导/统计检验/跨模型对比/Threats to Validity/可复现性附录）：

- 📄 **PDF版**：[Behavioral Fingerprinting of Large Language Models — Extended Tech Report](docs/tech_report.pdf)
- 🌐 **HTML版**：[tech_report.html](docs/tech_report.html)（在线阅读）
- 📝 **Markdown源**：[experiment_report.md](docs/experiment_report.md)
- 🧾 **Workshop投稿版（双盲精简版，LaTeX）**：[paper/](paper/) · [paper/main.pdf](paper/main.pdf)

**核心结论（均为同一中转站、in-distribution 结果）：**
- 行为画像能区分同家族两个标称端点（tokenizer 指纹做不到）
- 最强探针 TVD=0.90；"是否为 Okapi"规则重代入准确率 88%（Wilson [0.80,0.93]）；TVD≠准确率
- 管线自洽检验后验 0.913（CrI [0.885,0.937]），为 resubstitution，非 held-out
- 单次审计成本 < $0.01

**与前沿工作的关系**：我们的行为画像方法与 [One Token Is Enough](https://arxiv.org/abs/2607.10252)（单 token 输出分布指纹，EER 7.3%）互为补充——它聚焦跨家族谱系识别，我们在同家族两个标称端点上展示了可区分性；官方金标准基线与 held-out 泛化验证属未来工作。

## 项目结构

```
transit-truth/
├── index.html                  # 浏览器离线演示（GitHub Pages 入口；真实核验走 webapp/ + serve）
├── web/                        # Web 资源
├── standalone/index.html       # 跳转页（重定向到根 index.html）
├── backend/                    # Python 后端（FastAPI）
│   ├── app/
│   │   ├── core/              # 核心引擎（auditor/fingerprint/probes/
│   │   │                      #   statistical_analyzer/retry/balance_checker/...）
│   │   ├── verify/            # 无状态模型真实性核验（v1–v5：battery/reference/
│   │   │                      #   report/sequential/otel/reference_server）
│   │   ├── api/               # REST API
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 配置管理（14 个环境变量）
│   │   ├── tests/             # 离线桩 e2e + 统计/加固/集成测试（计数见顶部"测试"行）
│   │   └── main.py            # FastAPI 入口
│   └── requirements.txt
├── frontend/                   # Web 前端资源
├── data/
│   ├── baselines/              # 真实基准数据（经同一中转站采集）
│   │   ├── gpt-4o-mini.json
│   │   └── gpt-4o.json
│   └── fingerprints/           # 开源参考指纹目录（Qwen 真实 tokenizer 计数等）
├── docs/
│   ├── tech_report.tex         # 扩展技术报告 LaTeX 源
│   ├── tech_report.pdf / .html # 扩展技术报告
│   ├── experiment_report.md    # 实验报告 Markdown 源
│   ├── generate_tables.py      # 从 JSON 自动生成分布/TVD/卡方/分类器表
│   ├── make_fig.py             # 重画 fig_results.png
│   └── ...
├── paper/                      # 双盲精简 workshop 版（main.tex / main.pdf / fig_results.png）
├── examples/
├── collect_baseline.py         # 基准数据采集脚本（支持并发）
├── analyze_baseline.py         # 基准数据分析脚本
├── compare_models.py           # 跨模型对比分析脚本
├── Dockerfile / docker-compose.yml
├── pyproject.toml              # 源码安装配置（pip install -e .）
├── CHANGELOG.md / CONTRIBUTING.md / CODE_OF_CONDUCT.md / LICENSE
└── README.md
```

## 贡献指南

我们欢迎所有形式的贡献！

- **提交基准数据**：用`collect_baseline.py`采集你常用模型的基准数据，提交PR
- **贡献审计结果**：用工具审计你用的中转站，提交后进人工审核队列（`python -m app.moderation list/approve/reject`），审核通过才计入排行榜
- **开发新功能**：看GitHub Issues，认领任务
- **写文档/教程**：帮助更多人用上这个工具
- **报告Bug**：提交Issue，我们会尽快修复

详见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 免责声明

1. 本工具仅供学习和研究使用，请勿用于非法用途
2. 审计结果基于统计分析，仅供参考，不构成法律证据
3. 请遵守目标API服务的使用条款，不要对服务造成过大压力
4. 标记中转站为"可疑"不等于"确定造假"，请结合多方面信息判断
5. 本工具不对任何中转站的商业行为负责

## 许可证

MIT License

## 联系方式

- GitHub Issues：https://github.com/dafahaha/transit-truth/issues
- 邮箱：156556011+dafahaha@users.noreply.github.com

---

**如果你觉得这个工具有用，请给个Star ⭐，让更多人看到。**

> "你用的GPT-4是真的吗？30秒测出答案。"
