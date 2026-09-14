# TransitTruth 多平台推广文案合集

> 最后更新：2026-09-15
> 项目地址：https://github.com/dafahaha/transit-truth
> 在线Demo：https://dafahaha.github.io/transit-truth/

---

## 📊 项目核心卖点

1. **震撼发现**：GPT选数字100%返回7，选动物76%返回Okapi——大模型有"行为指纹"
2. **真实痛点**：80%以上AI API中转站存在模型偷偷降级，用户花了GPT-4的钱用的是GPT-3.5
3. **技术创新**：行为指纹可以区分同家族模型（gpt-4o vs gpt-4o-mini），tokenizer指纹做不到
4. **零门槛使用**：55KB单文件，浏览器打开即用，不需要安装，不需要后端
5. **全民共建**：中转站排行榜，5种贡献方式（GitHub/复制JSON/邮件/社区/API），无GitHub账号也能贡献
6. **学术潜力**：基于统计分析（卡方检验+KS检验+贝叶斯更新），可复现验证，有论文转化潜力

---

## 1️⃣ V2EX（中文技术社区）

**节点**：分享创造 / 程序员

**标题**：
```
我用27分钟发现了GPT的"行为指纹"：选数字100%返回7，做了个开源工具帮你验明正身
```

**正文**：
```
大家好，我是一名大三学生，最近在做AI API安全相关的研究。

你用的GPT-4是真的吗？中转站有没有偷偷给你降级成GPT-3.5？

我做了一个27分钟的小实验，发现了一个几乎没人注意到的现象：大语言模型在"随机"任务上有极端强烈的偏好，这些偏好可以用来"验明正身"。

## 震撼发现

- gpt-4o-mini选1-10的数字，**100%返回7**（零方差！）
- gpt-4o选随机动物，**76%返回Okapi**（㺢㹢狓，罕见非洲长颈鹿近亲）
- gpt-4o-mini掷骰子，**96%返回4**
- **只用"选一个随机动物"这一个探针，就能以90%准确率区分gpt-4o和gpt-4o-mini**——这是tokenizer指纹做不到的（两个模型用同一个o200k tokenizer）

## 为什么会这样？

大语言模型本质上是"下一个词预测器"。当你问它"选一个随机数字"时，它并不是真的在随机生成——它是在预测"在这种语境下，人类最可能说哪个数字"。

而训练数据里，数字的出现频率是极不均匀的：
- "7"因为文化原因（幸运数字、七宗罪、七大奇迹、一周七天）出现频率远高于其他数字
- "Okapi"可能在动物学相关的训练数据里被反复提及
- RLHF（人类反馈强化学习）又进一步放大了这些偏好

**结果就是：每个模型都有自己独特的"行为指纹"，就像每个人都有独特的说话习惯一样。**

## 这有什么用？

80%以上的AI API中转站存在模型偷偷降级（用mini冒充pro，用3.5冒充4）。但tokenizer指纹区分不了同家族的模型（gpt-4o和gpt-4o-mini用同一个tokenizer），而行为指纹可以。

## 我做了一个开源工具

基于这个发现，我做了 **TransitTruth**（AI API安全审计平台）：

- 🔍 行为指纹验证（14个探针，卡方检验+KS检验+贝叶斯更新）
- 📊 统计不确定性量化（Wilson置信区间+样本量评估）
- 💰 Token计费审计（检测中转站是否多计token）
- ⚡ 延迟与协议检查
- 💳 余额查询
- 🏆 中转站排行榜（12条初始数据，全民共建）
- 🚀 零安装在线Demo（55KB单文件，浏览器即用）
- 📋 5种贡献方式（GitHub/复制JSON/邮件/社区/API），无GitHub账号也能贡献

**在线体验**：https://dafahaha.github.io/transit-truth/
**GitHub**：https://github.com/dafahaha/transit-truth

打开链接，输入API Key，30秒就能测出你用的GPT是不是真的！

## 实验数据

- 26个探针（14行为+8 tokenizer+4能力），每个50次
- 2600次API请求，27分钟，$0成本（用免费中转站额度）
- 完整实验报告：https://github.com/dafahaha/transit-truth/blob/main/docs/experiment_report.md
- 基准数据已开源：https://github.com/dafahaha/transit-truth/tree/main/data/baselines

## 参考论文

- [One Token Is Enough](https://arxiv.org/abs/2607.10252)（2026）：单token指纹，165模型，EER 7.3%
- [CoIn](https://arxiv.org/abs/2505.13778)（2025）：API模型替换检测
- [RoFL](https://arxiv.org/abs/2505.12682)（2025）：鲁棒模型指纹

欢迎大家试用、提Issue、提交PR！有任何技术问题欢迎在评论区讨论。
```

---

## 2️⃣ 知乎（中文知识社区）

**专栏**：人工智能 / 机器学习

**标题**：
```
我用27分钟发现了GPT的"行为指纹"：选数字100%返回7，选动物76%返回Okapi
```

**正文**：
```
你用的GPT-4是真的吗？

如果你用过AI API中转站，可能会有这样的疑问：我付了GPT-4o的钱，实际用的是GPT-4o还是GPT-4o-mini？

最近我做了一个27分钟的小实验，发现了一个惊人的现象...

[此处粘贴完整爆文全文，参考 docs/blog_post.md]

---

**在线体验**：https://dafahaha.github.io/transit-truth/
**GitHub开源**：https://github.com/dafahaha/transit-truth

如果你觉得这个发现有意思，或者这个工具有用，欢迎点赞、收藏、关注！
```

---

## 3️⃣ 掘金（中文技术社区）

**分类**：人工智能 / 开源

**标题**：
```
我用27分钟发现了GPT的"行为指纹"，做了个开源工具帮你验明正身
```

**正文**：
```
## 前言

AI API中转站市场乱象频发，80%以上存在模型偷偷降级。但作为普通用户，你怎么验证自己用的中转站有没有"参水分"？

我做了一个27分钟的小实验，发现了GPT模型的"行为指纹"...

[此处粘贴爆文的"震撼发现"+"为什么会这样"+"这有什么用"部分]

## 我做了一个开源工具

基于这个发现，我做了 **TransitTruth**（AI API安全审计平台）。

### 在线体验

**零安装在线Demo**：https://dafahaha.github.io/transit-truth/

打开链接，输入API Key，30秒出结果。所有请求直接从浏览器发出，不需要后端服务器，不需要安装任何东西。

### 功能特性

- 🔍 **行为指纹验证**：14个行为探针（8英文+6中文），卡方检验+KS检验+贝叶斯更新
- 📊 **统计不确定性量化**：Wilson置信区间+样本量评估+95%可信区间
- 🔤 **Tokenizer指纹**：8个tokenizer探针，区分不同模型家族
- 🧠 **能力测试**：10个能力探针，估算模型等级
- 💰 **Token计费审计**：tiktoken精确计算，检测计费膨胀
- ⚡ **延迟与协议检查**：P50/P95/P99，7项协议合规
- 💳 **余额查询**：多中转站账户余额聚合
- 🏆 **中转站排行榜**：12条初始数据，全民共建，5种贡献方式
- 🚀 **纯前端在线Demo**：零安装，浏览器即用（55KB单文件，苹果风格设计）

### 技术栈

- 后端：Python + FastAPI + SQLite
- 前端：原生HTML/CSS/JS（无构建依赖）
- 统计：scipy（KS检验、卡方检验、贝叶斯更新）
- 部署：Docker / 本地运行 / 纯前端 / Vercel

### 零成本复现

```bash
# 1. 克隆项目
git clone https://github.com/dafahaha/transit-truth.git
cd transit-truth

# 2. 采集基准数据（用任何OpenAI兼容API即可）
python collect_baseline.py \
  --model gpt-4o-mini \
  --samples 50 \
  --base-url https://your-api-endpoint/v1 \
  --api-key sk-your-key \
  --output data/baselines/gpt-4o-mini.json \
  --concurrency 3

# 3. 分析结果
python analyze_baseline.py
```

## 最后

如果你觉得这个工具有用，欢迎给个Star ⭐，也欢迎提交PR一起完善。

**GitHub**：https://github.com/dafahaha/transit-truth
**在线Demo**：https://dafahaha.github.io/transit-truth/

标签：#人工智能 #开源 #Python #AI #GPT
```

---

## 4️⃣ Reddit r/LocalLLaMA（英文技术社区）

**标题**：
```
I discovered GPT's "behavioral fingerprint" in 27 minutes: it returns "7" 100% of the time when asked to pick a random number, and "Okapi" 76% of the time when asked to pick a random animal
```

**正文**：
```
Hey r/LocalLLaMA,

I'm a third-year CS student, and I recently did a 27-minute experiment that revealed something interesting about LLMs: they have extreme "behavioral fingerprints" on "random" tasks.

## Key Findings

- **gpt-4o-mini returns "7" 100% of the time** when asked to pick a random number from 1-10 (zero variance!)
- **gpt-4o returns "Okapi" 76% of the time** when asked to pick a random animal (Okapi is a rare African giraffe relative)
- **gpt-4o-mini returns "4" 96% of the time** when rolling a dice
- **A single probe ("pick a random animal") can distinguish gpt-4o from gpt-4o-mini with 90% accuracy** — something tokenizer fingerprints can't do (they use the same o200k tokenizer)

## Why this matters

80%+ of AI API relay services in China secretly downgrade models (charging for GPT-4o but serving GPT-4o-mini). Tokenizer fingerprints can't distinguish same-family models, but behavioral fingerprints can.

## What I built

I built **TransitTruth**, an open-source AI API security audit platform based on this finding:

- 🔍 Behavioral fingerprint verification (14 probes, chi-square + KS test + Bayesian update)
- 📊 Statistical uncertainty quantification (Wilson confidence intervals + sample size assessment)
- 🔤 Tokenizer fingerprints
- 💰 Token billing audit
- ⚡ Latency & protocol checks
- 💳 Balance checking
- 🏆 Community relay ranking (12 initial entries, 5 contribution methods)
- 🚀 Zero-install online demo (55KB single file, pure frontend)

**Live demo**: https://dafahaha.github.io/transit-truth/
**GitHub**: https://github.com/dafahaha/transit-truth

## Methodology

- 26 probes (14 behavioral + 8 tokenizer + 4 capability), 50 samples each
- 2600 total API requests, 27 minutes, $0 cost (using free relay credits)
- Statistical analysis: chi-square test + KS test + Bayesian update with 95% credible intervals
- Full experiment report: https://github.com/dafahaha/transit-truth/blob/main/docs/experiment_report.md
- Baseline data open-sourced: https://github.com/dafahaha/transit-truth/tree/main/data/baselines

## References

- [One Token Is Enough](https://arxiv.org/abs/2607.10252) (arXiv:2607.10252, 2026) — single-token fingerprinting, 165 models, EER 7.3%
- [CoIn](https://arxiv.org/abs/2505.13778) (arXiv:2505.13778, 2025) — API model substitution detection
- [RoFL](https://arxiv.org/abs/2505.12682) (arXiv:2505.12682, 2025) — robust model fingerprinting

Would love to hear your thoughts! Happy to answer any technical questions.

---

*All data is reproducible. Experiment scripts and baseline data are open-sourced.*
```

---

## 5️⃣ HackerNews（英文技术精英）

**标题**：
```
Show HN: I discovered GPT's behavioral fingerprint – it returns "7" 100% of the time for random numbers
```

**正文**：
```
I'm a CS student, and I recently discovered that LLMs have extreme "behavioral fingerprints" on "random" tasks:

- gpt-4o-mini returns "7" 100% of the time when asked to pick 1-10 (zero variance)
- gpt-4o returns "Okapi" 76% of the time when asked to pick a random animal
- A single probe can distinguish gpt-4o from gpt-4o-mini with 90% accuracy

This is useful for detecting AI API relay services that secretly downgrade models (charging for GPT-4o but serving GPT-4o-mini). Tokenizer fingerprints can't distinguish same-family models, but behavioral fingerprints can.

I built an open-source audit tool based on this:

- Live demo: https://dafahaha.github.io/transit-truth/
- GitHub: https://github.com/dafahaha/transit-truth
- 2600 API requests, 27 minutes, $0 cost
- Statistical method: chi-square + KS test + Bayesian update with 95% credible intervals
- Community ranking with 5 contribution methods (no GitHub account needed)

Paper reference: "One Token Is Enough" (arXiv:2607.10252)
```

---

## 6️⃣ 微信公众号（中文大众科普）

**标题**：
```
我用27分钟发现了GPT的秘密：选数字100%返回7，选动物76%返回Okapi
```

**正文**：
```
你用的GPT-4是真的吗？

最近AI API中转站特别火，几十块钱就能用GPT-4。但你有没有想过：你付了GPT-4的钱，实际用的可能是GPT-3.5？

我做了一个27分钟的小实验，发现了一个惊人的现象...

## 震撼发现

🔴 gpt-4o-mini选1-10的数字，**100%返回7**（零方差！）
🔴 gpt-4o选随机动物，**76%返回Okapi**（㺢㹢狓，罕见非洲长颈鹿近亲）
🔴 gpt-4o-mini掷骰子，**96%返回4**
🔴 只用"选动物"一个探针，就能以**90%准确率**区分gpt-4o和gpt-4o-mini

## 为什么会这样？

大语言模型本质上是"下一个词预测器"。当你问它"选一个随机数字"时，它并不是真的在随机生成——它是在预测"在这种语境下，人类最可能说哪个数字"。

而训练数据里，"7"因为文化原因（幸运数字、七宗罪、七大奇迹、一周七天）出现频率远高于其他数字。RLHF又进一步放大了这种偏好。

**结果就是：每个模型都有自己独特的"行为指纹"。**

## 怎么用？

我做了一个在线工具，零安装，打开就能用：

👉 https://dafahaha.github.io/transit-truth/

输入你的API Key，30秒就能测出你用的GPT是不是真的！

还有**中转站排行榜**，看看大家用的中转站哪些靠谱哪些坑。

## 最后

如果你觉得这个工具有用，欢迎分享给更多人！

GitHub开源：https://github.com/dafahaha/transit-truth

#AI #GPT #人工智能 #开源工具 #科技
```

---

## 7️⃣ 小红书（中文种草）

**标题**：
```
震惊！GPT选数字居然100%返回7😱 我做了个工具帮你验明正身
```

**正文**：
```
姐妹们！我发现了GPT的惊天秘密🤯

你们用的GPT-4可能是假的！！！

我做了个实验，发现GPT选数字居然100%返回7，选动物76%返回Okapi（什么鬼？㺢㹢狓是什么？）

原来每个大模型都有自己的"行为指纹"，就像每个人说话习惯不一样一样！

而80%的AI中转站都在偷偷降级！你花了GPT-4的钱，实际用的可能是GPT-3.5😡

于是我做了个工具👉TransitTruth

✅ 零安装，浏览器打开就能用
✅ 输入API Key，30秒出结果
✅ 行为指纹验证，能区分gpt-4o和gpt-4o-mini
✅ Token计费审计，看看有没有多扣你钱
✅ 中转站排行榜，看看哪些靠谱哪些坑
✅ 5种贡献方式，没有GitHub账号也能参与

在线体验🔗 https://dafahaha.github.io/transit-truth/

快看看你用的GPT是不是真的！评论区告诉我你的结果👇

#AI #GPT #人工智能 #开源工具 #科技 #避坑 #中转站
```

---

## 8️⃣ B站视频脚本（中文视频）

**标题**：
```
【硬核】我用27分钟发现了GPT的"行为指纹"：选数字100%返回7！做了个开源工具帮你验明正身
```

**视频脚本**：
```
【开场：0-15秒】
（画面：快速剪辑GPT回答"选一个1-10的数字"，每次都返回7）
旁白：你相信吗？GPT选数字，100%返回7。选动物，76%返回Okapi。这不是bug，这是大模型的"行为指纹"。

【第一部分：15-60秒 震撼发现】
（画面：实验数据图表，Okapi动物图片）
旁白：我是一名大三学生，最近做了一个27分钟的小实验，2600次API请求，发现了一个惊人的现象。
- gpt-4o-mini选1-10的数字，100%返回7，零方差！
- gpt-4o选随机动物，76%返回Okapi，就是这个罕见的非洲长颈鹿近亲。
- 只用"选动物"一个探针，就能以90%准确率区分gpt-4o和gpt-4o-mini。

【第二部分：60-120秒 为什么会这样】
（画面：大模型原理图，训练数据词频图）
旁白：为什么会这样？大语言模型本质上是"下一个词预测器"。当你问它"选一个随机数字"时，它并不是真的在随机生成，而是在预测"人类最可能说哪个数字"。
而"7"因为文化原因——幸运数字、七宗罪、七大奇迹、一周七天——出现频率远高于其他数字。RLHF又进一步放大了这种偏好。
结果就是：每个模型都有自己独特的"行为指纹"。

【第三部分：120-180秒 这有什么用】
（画面：中转站价格对比图，降级示意图）
旁白：这有什么用？80%以上的AI API中转站存在模型偷偷降级——你花了GPT-4的钱，实际用的可能是GPT-3.5。
但tokenizer指纹区分不了同家族的模型，因为gpt-4o和gpt-4o-mini用同一个tokenizer。而行为指纹可以。

【第四部分：180-240秒 我做了什么】
（画面：TransitTruth在线Demo演示，输入API Key，审计过程，结果展示）
旁白：基于这个发现，我做了一个开源工具——TransitTruth，AI API安全审计平台。
- 零安装，55KB单文件，浏览器打开就能用
- 输入API Key，30秒出结果
- 行为指纹验证，14个探针，卡方检验+KS检验+贝叶斯更新
- Token计费审计，看看有没有多扣你钱
- 延迟与协议检查
- 中转站排行榜，全民共建
- 5种贡献方式，没有GitHub账号也能参与

【第五部分：240-270秒 怎么用】
（画面：手机/电脑打开在线Demo，输入API Key，点击开始审计）
旁白：怎么用？打开链接，输入你的API Key，点击开始审计，30秒就能测出你用的GPT是不是真的！
链接在评论区置顶，快去试试吧！

【结尾：270-300秒】
（画面：GitHub仓库页面，Star按钮高亮）
旁白：如果你觉得这个工具有用，欢迎给个Star，也欢迎提交PR一起完善。
我是一名大三学生，正在申请美国PhD，你的支持对我很重要！
我们下期再见！

【视频信息】
- 时长：约5分钟
- 封面：GPT选数字100%返回7的截图 + 大字标题
- 标签：#AI #GPT #人工智能 #开源 #编程 #科技
```

---

## 9️⃣ 微博（中文短文本）

**文案1（发现类）**：
```
震惊！我用27分钟做了2600次API请求，发现GPT选数字100%返回7，选动物76%返回Okapi（㺢㹢狓？）。原来每个大模型都有自己的"行为指纹"！

而80%的AI中转站都在偷偷降级…你花了GPT-4的钱，用的可能是GPT-3.5😡

我做了个开源工具帮你验明正身，零安装浏览器即用👉
https://dafahaha.github.io/transit-truth/

#AI #GPT #人工智能 #开源 #科技
```

**文案2（工具类）**：
```
推荐一个AI API中转站验真工具——TransitTruth🔍

输入API Key，30秒测出：
✅ 你的GPT是不是真的（行为指纹验证）
✅ 有没有多扣你Token（计费审计）
✅ 延迟和协议是否正常
✅ 中转站排行榜，看看哪些靠谱哪些坑

零安装，55KB单文件，浏览器打开就能用👉
https://dafahaha.github.io/transit-truth/

GitHub开源：https://github.com/dafahaha/transit-truth

#AI #GPT #避坑 #开源工具
```

---

## 🔟 Twitter/X（英文短文本）

**文案1（发现类）**：
```
I discovered GPT's "behavioral fingerprint" in 27 minutes:
- It returns "7" 100% of the time when asked to pick 1-10 (zero variance!)
- It returns "Okapi" 76% of the time when asked to pick a random animal
- A single probe distinguishes gpt-4o from gpt-4o-mini with 90% accuracy

80%+ of AI API relays secretly downgrade models. I built an open-source tool to detect it:

🔗 https://dafahaha.github.io/transit-truth/
🐙 https://github.com/dafahaha/transit-truth

#AI #LLM #OpenSource #GPT
```

**文案2（工具类）**：
```
Check if your AI API relay is secretly downgrading your model 🔍

TransitTruth:
✅ Behavioral fingerprint verification (14 probes)
✅ Token billing audit
✅ Latency & protocol checks
✅ Community ranking
✅ Zero-install, 55KB single file, browser-ready

🔗 https://dafahaha.github.io/transit-truth/
🐙 https://github.com/dafahaha/transit-truth

#AI #LLM #OpenSource #Security
```

---

## 📅 发布策略

### 第一波（发布当天）
1. **V2EX**（上午10:00）- 技术社区首发，获取早期反馈
2. **掘金**（下午14:00）- 工具类社区，获取Star
3. **知乎**（晚上20:00）- 详细科普，获取关注
4. **微博**（晚上21:00）- 短文本扩散

### 第二波（发布后1-2天）
5. **Reddit r/LocalLLaMA**（美国时间上午）- 英文社区，获取国际关注
6. **HackerNews**（美国时间上午）- 技术精英社区，获取高质量讨论
7. **Twitter/X**（美国时间中午）- 英文短文本扩散

### 第三波（发布后3-7天）
8. **微信公众号** - 大众科普，获取非技术用户
9. **小红书** - 种草平台，获取女性用户
10. **B站视频** - 视频演示，获取更大流量

---

## ✅ 发布前检查清单

- [ ] GitHub仓库已公开
- [ ] README已完善（含在线Demo链接）
- [ ] GitHub Pages已部署：https://dafahaha.github.io/transit-truth/
- [ ] 在线Demo可正常访问和使用
- [ ] 排行榜功能正常（12条数据，筛选/排序/搜索）
- [ ] 多渠道贡献功能正常（5种方式）
- [ ] 46个单元测试全部通过
- [ ] 15个API端点正常
- [ ] CLI工具正常（audit/list/export/benchmark/balance）
- [ ] Topics已设置（ai, llm, openai, api, security, fingerprint, audit, gpt）
- [ ] 仓库已Pinned到个人主页
- [ ] 爆文已写好：docs/blog_post.md
- [ ] 多平台文案已准备：docs/final_release_package.md
- [ ] 部署指南已准备：docs/deployment_guide.md
- [ ] Social Preview已设置

---

## 📊 跟踪指标

### 第一周目标
- GitHub Stars：100+
- 在线Demo访问量：1000+
- 社区讨论：V2EX/知乎/Reddit/HN各有至少10条评论
- PR/Issue：至少有3个外部贡献
- 排行榜贡献：至少有5个用户提交审计结果

### 跟踪方式
- GitHub Stars：https://github.com/dafahaha/transit-truth/stargazers
- 访问量：GitHub Insights → Traffic
- 社区讨论：搜索"TransitTruth"或"行为指纹"
- 贡献者：https://github.com/dafahaha/transit-truth/graphs/contributors

---

## ⚠️ 注意事项

1. **不要过度营销**：重点放在技术发现和开源精神，不要像广告
2. **回复评论要专业**：虚心接受批评，认真回答技术问题
3. **保守表述**：审计结果基于统计分析，不要说"100%准确"
4. **不要点名具体中转站**：用"某中转站"等保守表述，避免法律风险
5. **保护用户隐私**：不要在公开场合展示用户的API Key或个人信息
6. **学术诚信**：明确说明这是初步研究，欢迎同行验证和批评

---

**祝你发布顺利，项目爆火！🚀**
