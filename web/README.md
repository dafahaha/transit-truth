# TransitTruth 纯前端在线Demo

这是 TransitTruth 的纯前端版本，**不需要后端服务器**，所有 API 请求直接从浏览器发出。

## 特性

- ✅ **零部署成本**：纯静态文件，可直接部署到 GitHub Pages
- ✅ **隐私安全**：API Key 只在浏览器本地使用，不会发送到任何第三方服务器
- ✅ **一键检测**：输入 API Key，30秒出结果
- ✅ **多维度检测**：延迟、Token计数、模型指纹、能力测试
- ✅ **本地历史**：检测历史保存在浏览器 localStorage

## 使用方法

### 方式1：直接打开（本地使用）

直接用浏览器打开 `index.html` 文件即可使用。

### 方式2：部署到 GitHub Pages

1. 将 `web/` 目录的内容推送到 GitHub 仓库
2. 在仓库 Settings → Pages 中选择 `main` 分支的 `/web` 目录
3. 访问 `https://<your-username>.github.io/<repo-name>/web/`

### 方式3：本地启动 HTTP 服务器

```bash
cd web
python -m http.server 8080
# 然后访问 http://localhost:8080
```

## 检测维度

| 维度 | 说明 | 权重 |
|------|------|------|
| ⏱️ 延迟检测 | 3次请求的平均延迟 | 15% |
| 🔢 Token计数 | 对比报告的tokens与tiktoken计算的预期值（含chat template开销） | 30% |
| 🔍 模型指纹 | tokenizer探针 + 行为探针，检测是否与声称模型一致 | 30% |
| 🧠 能力测试 | 数学、逻辑、推理、指令遵循，估算模型等级 | 25% |

## 检测模式

- **快速检测**（~10秒）：3个tokenizer探针 + 4个行为探针 + 4个能力探针
- **深度检测**（~60秒）：更多探针，更高置信度

## 技术说明

### Token计数

使用 [@dqbd/tiktoken](https://github.com/dqbd/tiktoken) 的 JS 版本（cl100k_base 编码）在浏览器端计算预期 token 数。

**注意**：API 返回的 prompt_tokens 包含 chat template 开销（system/user/assistant 标记），而 tiktoken 计算的是 raw text 的 token 数。因此我们估算了约 12 tokens 的 chat template 开销，并将"膨胀率"改称为"差异率"，避免误报。

### 模型指纹

通过以下方式检测模型是否被偷偷降级：
1. **Tokenizer 探针**：特定字符串在不同模型的 tokenizer 下会产生不同的 token 数
2. **行为探针**：随机数生成、颜色命名等任务，不同模型有不同的分布偏好
3. **能力测试**：数学、逻辑、推理等任务，低阶模型通过率较低

### 隐私保护

- API Key 只在浏览器内存中使用，不会存储到 localStorage
- 所有 API 请求直接发送到用户指定的中转站，不经过任何中间服务器
- 检测历史只存储评分和元数据，不存储 API Key

## 免责声明

本工具仅供用户验证自己使用的服务，检测结果基于有限样本，不构成对任何服务的最终评价。Token 差异率包含 chat template 开销，不等同于造假。模型指纹检测为概率性判断，置信度低于 80% 时不构成模型降级的证据。

## 与后端版本的区别

| 特性 | 纯前端版本 | 后端版本 |
|------|-----------|---------|
| 部署成本 | 零（GitHub Pages） | 需要服务器 |
| 隐私保护 | 极高（Key不离浏览器） | 高（Key不存储） |
| 检测深度 | 中等 | 高（更多探针） |
| 排行榜贡献 | 手动跳转GitHub Issue | 一键自动提交 |
| 持续监控 | 不支持 | 支持 |
| 批量审计 | 不支持 | 支持 |

纯前端版本适合**快速验证和传播**，后端版本适合**深度检测和学术研究**。
