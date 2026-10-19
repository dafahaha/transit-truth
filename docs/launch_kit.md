# Launch kit

> ⚠️ **冻结 / 历史状态（v0.5.2）**：本文件是旧版"纯前端浏览器演示"时期的发布文案草稿，已被取代、不再维护。其中"零安装 / 纯前端 / Key 不经过任何服务器"等表述已过时：**当前模型身份核验（测中转站真假）必须在本地/自托管运行 `transit-truth serve`**（浏览器跨域直连受 CORS 限制，GitHub Pages 不能在线实测）；测试数与一切口径以 README.md 为准，勿直接照搬以下文案对外发布。

Copy-paste launch posts for each channel. Nothing here is scheduled or sent by anyone but you.
All claims match the current README/verify.md — do not upgrade the tone. This tool outputs
**probabilistic auxiliary evidence**, not proof; keep saying so in every version.

Links to keep consistent:

- Repo: https://github.com/dafahaha/transit-truth
- Demo (zero install): https://dafahaha.github.io/transit-truth/
- PyPI (once published): https://pypi.org/project/transit-truth/

---

## 1. V2EX（中文）

**标题：** 写了个小工具：核验 OpenAI 兼容中转站到底有没有给你声称的那个模型

**正文：**

用中转站调 API 的时候，你付的是 `gpt-4o-mini` 的钱，怎么确定后端真的是 gpt-4o-mini，而不是更便宜的模型在套壳？公开研究里类似情况不少：一项 ACM CCS 2026 研究（arXiv:2603.01919）在 3 个代表性 shadow API × 8 种配置上测得 45.83%（11/24）端点过不了模型指纹；另一项恶意中介供应链攻击测量（arXiv:2604.08407《Your Agent Is Mine: Measuring Malicious Intermediary Attacks on the LLM Supply Chain》）在 428 个路由（28 付费 + 400 免费）中发现 9 起投毒、17 个触碰 AWS 金丝雀凭证、1 起 ETH 私钥 draining；另有据媒体转述的知道创宇《大模型中转站研究与测评报告（2026）》（原始报告链接待补，非一手权威）称 100 站、849 组合中 296 个（34.9%）命中至少一项模型真实性异常证据（涉 75 站，467 可疑 / 138 强证据）。但一直没有一个随手能跑的核验工具。

所以我写了 TransitTruth：一个无状态 CLI，对着任意 OpenAI 兼容端点发一组有界探针（17 个请求；按公开低档定价估算一轮约 <$0.01，实际取决于模型档位与单价，代码不含计价逻辑），输出一份 JSON：

- `pass`：观测指纹和参考一致
- `suspicious`：差异显著（比如模型家族不对）
- `insufficient_evidence`：没有参考 / 样本太小 / 端点不配合——不瞎猜

它不假装是密码学证明，README 里把局限写得很直白：
- 现在内置参考只有 Qwen2.5-0.5B 的本地 tokenizer 指纹，和一个单次采集的 GPT 基线（来自单个中转站，不是官方端点）
- temperature=0 的行为基线是退化分布，公开探针意味着对手可以硬编码复现，报告会显式标 `deterministic_replay_risk` 并把置信度压到 low
- tokenizer 计数是自报信号，弱证据

没有付费 key 也能跑：自带一个本地 reference-server，dummy key 就能把整条链路跑一遍自检。GitHub Pages 仅为离线演示（内置种子数据，不发送 key）；真实核验请在本地/自托管运行 `transit-truth serve`，浏览器直连受 CORS 限制。

MIT 协议，测试 352 passed / 7 skipped（7 skipped 为需真实 key 的 integration）。欢迎拿你常用的站跑一遍，结果贴 Discussion 里（别贴 key）。

**评论区置顶：**
> FAQ 见 https://github.com/dafahaha/transit-truth/discussions/2 。suspicious 不等于实锤欺诈，只是值得去找 provider 要个说法。

---

## 2. 即刻（中文，短）

**正文：**

做了个小工具 TransitTruth：给 OpenAI 兼容中转站做模型身份核验。
17 个探针；按公开低档定价估算一轮约 <$0.01（实际取决于模型档位与单价，代码不含计价逻辑），输出 pass / suspicious / insufficient_evidence 三态 JSON。
诚实声明：这是概率性辅助证据不是密码学证明；目前只内置了 Qwen tokenizer 指纹和单站 GPT 基线。没 key 也能跑，自带本地 reference-server。
repo：github.com/dafahaha/transit-truth，demo 在 GitHub Pages 零安装可玩。

---

## 3. X / Twitter（英文）

**Post:**

You pay a relay for `gpt-4o-mini`. How do you know that's what you got?

I built TransitTruth: a stateless CLI that probes any OpenAI-compatible endpoint with a bounded battery (17 requests; at public low-tier list prices a full run estimates under $0.01; actual cost depends on model tier and per-token price, and the code contains no pricing logic) and returns one JSON verdict — `pass`, `suspicious`, or `insufficient_evidence`.

It is deliberately honest about what it is NOT:

- probabilistic auxiliary evidence, not a cryptographic proof
- shipped references today: one open Qwen2.5 tokenizer fingerprint + a single-collected GPT baseline
- temperature=0 replay risk is flagged explicitly in the report

No paid key needed: ships a local reference server, so you can exercise the whole pipeline locally. Zero-install demo in-browser.

repo + demo links below. MIT.

---

## 4. Reddit r/LocalLLaMA（英文）

**Title:** I open-sourced TransitTruth: a CLI that probes OpenAI-compatible relays to verify the model they claim to serve (17 probes; estimates under $0.01/run at public low-tier list prices, three honest verdicts)

**Body:**

I got tired of the "am I actually getting the model I paid for?" problem with API relays, so I built a small CLI called TransitTruth.

What it does: point it at any OpenAI-compatible endpoint with a claimed model. It sends a bounded battery of 17 requests (5 tokenizer probes using self-reported `usage.prompt_tokens` on a fixed prompt suite, plus 4 behavioral probes × 3 repeats — "pick a number 1–10", coin flips, that sort of distributional fingerprint), compares against a shipped reference catalog with chi-square / KS tests and a Bayesian posterior, and returns one JSON:

- `pass` — observed fingerprint statistically consistent with reference
- `suspicious` — significant mismatch (e.g. wrong model family)
- `insufficient_evidence` — no reference / small sample / endpoint refused; it does NOT guess

Important, stated up front in the README:

1. This is probabilistic auxiliary evidence, not a cryptographic proof. Black-box fingerprints can be faked; provider-signed attestations are the real endgame. This is a cheap repeatable screening layer.
2. Coverage is narrow by design right now: Qwen2.5-0.5B local tokenizer counts (no behavioral distribution, so it alone never yields `pass`), plus a GPT baseline collected through a single third-party relay, not the official OpenAI endpoint.
3. temperature=0 point-mass replay risk: the behavioral baselines are degenerate distributions and the probes are public, so an adversary can hard-code the public modal strings. The report flags `deterministic_replay_risk` and caps confidence at `low`.
4. Tokenizer counts are self-reported and weak; behavior is the primary judge.

You can run the whole thing without a paid key — it ships a local reference server (dummy key, loopback, `--allow-local`). There's also a zero-install browser demo.

MIT, 352 passed / 7 skipped (7 skipped = integration tests needing a real key). If you audit a relay you use, I set up a discussion thread to post results — please never paste keys.

---

## 5. 中文 API 中转站社区 / 微信群（中文，私聊转发版）

**正文：**

各位站长/用户，分享一个刚开源的小工具 TransitTruth（MIT）：核验 OpenAI 兼容端点声称的模型和实际跑的是否一致。

用法（注意：包尚未发布到 PyPI，`pip install transit-truth` 发布后才可用；当前从源码 `pip install -e .`）：
```
# 发布后替换为：pip install transit-truth；当前：pip install -e .
export TRANSIT_TRUTH_API_KEY=你的key
transit-truth verify --base-url https://你的站/v1 --model gpt-4o-mini
```
一次 17 个请求；按公开低档定价估算一轮约 <$0.01（实际取决于模型档位与单价，代码不含计价逻辑），输出 pass / suspicious / insufficient_evidence。

对站长：这个工具不会搞事——suspicious 只是"证据值得复核对质"，不是定罪；报告里自带 disclaimer。欢迎把它当自我核验的基线：先自己跑一遍自家站，确认声称的模型都过得了，再给用户一个可自查的说法。

对用户：跑之前看一眼 README 的 limitations——现在内置参考很窄，只有 Qwen tokenizer 指纹和单站 GPT 基线；结果是概率性辅助证据，别拿来当吵架的锤。

repo：github.com/dafahaha/transit-truth；零安装 demo 在 GitHub Pages。

---

## Master FAQ（被问到时照这个答）

**Q: 为什么不用官方的 cryptographic attestation？**
A: 好问题，而且这正是 endgame。官方签名响应才是唯一硬证据。但今天大多数第三方中转/网关根本不提供任何 attestation，用户手里只有一个 HTTP 端点。这个工具是在 attestation 存在之前的廉价筛查层——不是替代品。

**Q: 这是不是伪科学？**
A: 它是概率性辅助证据，不是密码学证明，README 第一屏就写了。suspicious 不等于"你是骗子"，等于"这个差异值得你拿着报告去找 provider 要个解释"。报告里有 `deterministic_replay_risk` 这类自曝条款。

**Q: 开源模型指纹为什么只有 1 个？**
A: 现在本地目录只有 Qwen2.5-0.5B-Instruct 的真实 tokenizer 计数（DeepSeek-R1-Distill-Qwen 派生自同一 tokenizer，区分不开）；GLM 在目录里但 tokenizer 待下载。加新模型指纹是专门的 good-first-issue，欢迎提 PR。

**Q: 会不会误伤（把正经站判成 suspicious）？**
A: 会有风险，所以才设计了三态：参考缺失/样本不足时直接给 `insufficient_evidence` 而不是硬判。温度=0 的退化基线本来就会把置信度压到 low。建议站长先拿自家站自检基线。

**Q: 收费吗？key 安全吗？**
A: MIT 免费。key 只从环境变量读，不落盘、不进日志、不进报告；报告 JSON 里没有任何 key 字段。GitHub Pages 离线演示本身不发送 key；真实核验走本地/自托管 `transit-truth serve`，key 仅在本地内存，不进分享报告。

---

## 发布后 48 小时运营清单

- **在哪回复**
  - GitHub Issues：每提必看，24h 内首响；bug 类先复现，feature 类先对齐范围。
  - Discussions #2（Welcome/FAQ）：把重复问题沉淀成新 FAQ 条目。
  - V2EX / Reddit / X：发布后前 6 小时蹲评论区；尖刻质疑优先回，赞同不回。
  - 微信群/社区：有人贴核验结果时引导他们发到 Discussion #3。
- **怎么收 issue**
  - 贴了真实站 suspicious 结果 → 请对方脱敏（去掉 key，保留 base URL 域名）后转 Discussion #3。
  - 报"结果不准" → 先要 `--model`、base URL、完整 JSON 报告；对照 verify.md 的报告合同判断是覆盖不足还是 bug。
- **怎么把反馈转成 good-first-issue**
  - 用户想要某个模型指纹 → 对照 issue #4 的模板开新 issue，列清数据 schema 与 sync 步骤。
  - 用户要某个观测/导出集成 → 对照 issue #5（OTel exporter）开新 issue。
  - 翻译请求 → 对照 issue #6 开新 issue。
- **awesome PR 跟踪**
  - 记录三个 PR 的合并/关闭结果；被要求改格式就改，被拒就记录原因不反复争论。
- **PyPI**
  - 发布动作必须本人执行，见 docs/PUBLISHING.md；上线后回来把各渠道文案里的 PyPI 链接补全。
