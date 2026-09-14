# TransitTruth 多平台发布指南

> 本文档包含各平台的发布文案、注意事项和最佳实践。

---

## 📋 发布前检查清单

- [ ] GitHub仓库已公开
- [ ] README已完善（含在线Demo链接）
- [ ] GitHub Pages已部署：https://dafahaha.github.io/transit-truth/
- [ ] Topics已设置（ai, llm, openai, api, security, fingerprint, audit, gpt）
- [ ] Social Preview已上传
- [ ] 仓库已Pinned到个人主页
- [ ] 爆文已写好：docs/blog_post.md
- [ ] 演示视频/GIF已准备好

---

## 🌐 平台1：V2EX

**节点选择**：分享创造 / 程序员

**标题**：
```
我用27分钟发现了GPT的"行为指纹"：选数字100%返回7，选动物76%返回Okapi
```

**正文**（直接使用爆文，开头加一句V2EX风格的问候）：
```
大家好，我是一名大三学生，最近在做AI API安全相关的研究。

[此处粘贴爆文全文]

在线Demo：https://dafahaha.github.io/transit-truth/
GitHub：https://github.com/dafahaha/transit-truth

欢迎大家试用、提Issue、提交PR！
```

**注意事项**：
- V2EX用户技术水平高，喜欢有深度的技术分享
- 不要过度营销，重点放在技术发现和开源精神
- 回复评论时保持专业，虚心接受批评
- 可以在评论区补充技术细节

---

## 📚 平台2：知乎

**专栏选择**：人工智能 / 机器学习 / 程序员

**标题**：
```
我用27分钟发现了GPT的"行为指纹"：选数字100%返回7，选动物76%返回Okapi
```

**正文**（使用爆文，开头加知乎风格的引言）：
```
你用的GPT-4是真的吗？

如果你用过AI API中转站，可能会有这样的疑问：我付了GPT-4o的钱，实际用的是GPT-4o还是GPT-4o-mini？

最近我做了一个27分钟的小实验，发现了一个几乎没人注意到的现象...

[此处粘贴爆文全文]
```

**注意事项**：
- 知乎用户喜欢详细、有逻辑的科普文章
- 可以适当加入一些背景知识（什么是tokenizer、什么是RLHF）
- 图片要清晰，数据要准确
- 回答评论时要有耐心，知乎用户喜欢追问细节
- 可以在文末引导关注和点赞

---

## 💎 平台3：掘金

**分类选择**：人工智能 / 前端 / 开源

**标题**：
```
我用27分钟发现了GPT的"行为指纹"，做了一个开源工具帮你验明正身
```

**正文**（使用爆文，重点突出工具和开源）：
```
## 前言

AI API中转站市场乱象频发，80%以上存在模型偷偷降级。但作为普通用户，你怎么验证自己用的中转站有没有"参水分"？

我做了一个27分钟的小实验，发现了GPT模型的"行为指纹"...

[此处粘贴爆文全文，重点突出"我做了一个开源工具"部分]

## 在线体验

零安装在线Demo：https://dafahaha.github.io/transit-truth/

打开链接，输入API Key，30秒出结果。

## 技术栈

- 后端：Python + FastAPI + SQLite
- 前端：原生HTML/CSS/JS（无构建依赖）
- 统计：scipy（KS检验、卡方检验、贝叶斯更新）

## 最后

如果你觉得这个工具有用，欢迎给个Star ⭐，也欢迎提交PR一起完善。

GitHub：https://github.com/dafahaha/transit-truth
```

**注意事项**：
- 掘金用户喜欢实用工具和开源项目分享
- 重点突出"零安装在线Demo"和"技术栈"
- 代码块要格式化好
- 可以加入一些截图和演示GIF
- 标签：#人工智能 #开源 #Python #AI

---

## 🤖 平台4：Reddit r/LocalLLaMA

**标题**：
```
I discovered GPT's "behavioral fingerprint" in 27 minutes: it returns "7" 100% of the time when asked to pick a random number, and "Okapi" 76% of the time when asked to pick a random animal
```

**正文**（英文精简版）：
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
- 🚀 Zero-install online demo (55KB single file, pure frontend)

**Live demo**: https://dafahaha.github.io/transit-truth/
**GitHub**: https://github.com/dafahaha/transit-truth

## Methodology

- 26 probes (14 behavioral + 8 tokenizer + 4 capability), 50 samples each
- 2600 total API requests, 27 minutes, $0 cost (using free relay credits)
- Statistical analysis: chi-square test + KS test + Bayesian update with 95% credible intervals

## References

- [One Token Is Enough](https://arxiv.org/abs/2607.10252) (arXiv:2607.10252, 2026) — single-token fingerprinting, 165 models, EER 7.3%
- [CoIn](https://arxiv.org/abs/2505.13778) (arXiv:2505.13778, 2025) — API model substitution detection
- [RoFL](https://arxiv.org/abs/2505.12682) (arXiv:2505.12682, 2025) — robust model fingerprinting

Would love to hear your thoughts! Happy to answer any technical questions.

---

*All data is reproducible. Experiment scripts and baseline data are open-sourced.*
```

**注意事项**：
- r/LocalLLaMA用户技术水平很高，对LLM内部机制感兴趣
- 重点突出技术发现和统计方法
- 不要过度营销，保持学术讨论的语气
- 回复评论时要有技术深度
- 可以讨论"为什么会有这种偏好"等学术问题

---

## 🔬 平台5：HackerNews

**标题**：
```
Show HN: I discovered GPT's behavioral fingerprint – it returns "7" 100% of the time for random numbers
```

**正文**（极简版，HN用户不喜欢长文）：
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

Paper reference: "One Token Is Enough" (arXiv:2607.10252)
```

**注意事项**：
- HN用户喜欢简洁、有技术深度的内容
- 标题要吸引人但不要标题党
- 正文控制在300字以内
- 重点放在"发现"和"工具"上
- 不要在正文里放太多链接，1-2个就够了
- 回复评论时要快速、专业

---

## 📱 平台6：微信公众号 / 小红书

**标题**（公众号）：
```
我用27分钟发现了GPT的秘密：选数字100%返回7，选动物76%返回Okapi
```

**标题**（小红书）：
```
震惊！GPT选数字居然100%返回7😱 我做了个工具帮你验明正身
```

**正文**（科普风格，适合非技术用户）：
```
你用的GPT-4是真的吗？

最近AI API中转站特别火，几十块钱就能用GPT-4。但你有没有想过：你付了GPT-4的钱，实际用的可能是GPT-3.5？

我做了一个27分钟的小实验，发现了一个惊人的现象...

[此处使用爆文，但语言要更通俗，减少技术术语]

## 怎么用？

我做了一个在线工具，零安装，打开就能用：

👉 https://dafahaha.github.io/transit-truth/

输入你的API Key，30秒就能测出你用的GPT是不是真的！

## 最后

如果你觉得这个工具有用，欢迎分享给更多人！

GitHub开源：https://github.com/dafahaha/transit-truth
```

**注意事项**：
- 公众号/小红书用户技术水平较低，要通俗易懂
- 多用emoji和分段，少用技术术语
- 重点放在"发现"和"怎么用"上
- 图片要大、要清晰
- 可以加入一些"震惊体"标题，但不要过度

---

## 🎯 发布策略建议

### 第一波（发布当天）
1. **V2EX**（上午10点）- 技术社区首发，获取早期反馈
2. **掘金**（下午2点）- 工具类社区，获取Star
3. **知乎**（晚上8点）- 详细科普，获取关注

### 第二波（发布后1-2天）
4. **Reddit r/LocalLLaMA**（根据美国时间，晚上发布）- 英文社区，获取国际关注
5. **HackerNews**（美国时间上午）- 技术精英社区，获取高质量讨论

### 第三波（发布后3-7天）
6. **微信公众号/小红书** - 大众科普，获取非技术用户
7. **B站/抖音视频**（如果有精力）- 视频演示，获取更大流量

### 关键指标
- GitHub Stars：目标100+（第一周）
- 在线Demo访问量：目标1000+（第一周）
- 社区讨论：V2EX/知乎/Reddit/HN各有至少10条评论
- PR/Issue：至少有3个外部贡献

---

## ⚠️ 风险提示

1. **中转站可能会防御**：如果项目火了，中转站可能会对"随机"问题做特殊处理。但这会增加成本，而且很难对所有探针都防御。

2. **法律风险**：审计结果基于统计分析，不构成法律证据。不要在公开场合点名具体中转站"造假"，用"可疑"等保守表述。

3. **API滥用**：请遵守目标API的使用条款，不要对服务造成过大压力。工具是为了帮助用户保护自己的权益，不是为了攻击中转站。

4. **模型更新**：OpenAI更新模型后，行为指纹可能会变化。需要定期更新基准数据库。

---

## 📞 联系方式

- GitHub Issues：https://github.com/dafahaha/transit-truth/issues
- 邮箱：ldz@e.gzhu.edu.cn

---

**祝你发布顺利，项目爆火！🚀**
