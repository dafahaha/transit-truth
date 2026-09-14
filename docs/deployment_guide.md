# 部署指南 (Deployment Guide)

TransitTruth 支持多种部署方式，从一键部署到本地运行，满足不同用户的需求。

---

## 目录

- [快速部署（推荐）](#快速部署推荐)
  - [Vercel（国内可访问）](#vercel国内可访问)
  - [Netlify](#netlify)
  - [GitHub Pages](#github-pages)
- [本地运行](#本地运行)
  - [纯前端版本（零安装）](#纯前端版本零安装)
  - [完整后端版本](#完整后端版本)
  - [Docker 部署](#docker-部署)
- [国内访问优化](#国内访问优化)
- [自定义域名](#自定义域名)
- [常见问题](#常见问题)

---

## 快速部署（推荐）

### Vercel（国内可访问）

Vercel 是最快的部署方式，全球 CDN 加速，国内访问速度良好。

#### 一键部署

点击下方按钮，一键部署到 Vercel：

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fdafahaha%2Ftransit-truth)

#### 手动部署

```bash
# 1. 安装 Vercel CLI
npm install -g vercel

# 2. 登录
vercel login

# 3. 部署
cd transit-truth
vercel --prod
```

#### 配置

项目根目录已包含 `vercel.json` 配置文件，无需额外配置。

- **构建命令**：无（纯静态文件）
- **输出目录**：根目录
- **默认页面**：`index.html`（纯前端在线Demo）

#### 优势

- ✅ 全球 CDN 加速，国内访问速度良好
- ✅ 免费额度充足（100GB 带宽/月）
- ✅ 自动 HTTPS
- ✅ 自动部署（GitHub 推送后自动更新）
- ✅ 自定义域名支持

---

### Netlify

Netlify 也是一个优秀的静态网站托管平台。

#### 一键部署

[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/dafahaha/transit-truth)

#### 手动部署

```bash
# 1. 安装 Netlify CLI
npm install -g netlify-cli

# 2. 登录
netlify login

# 3. 部署
cd transit-truth
netlify deploy --prod
```

#### 配置

创建 `netlify.toml`：

```toml
[build]
  publish = "."
  command = ""

[[headers]]
  for = "/*"
  [headers.values]
    X-Content-Type-Options = "nosniff"
    X-Frame-Options = "DENY"
```

---

### GitHub Pages

GitHub Pages 是最直接的部署方式，但国内访问可能不稳定。

#### 已配置

本项目已配置 GitHub Pages，访问地址：

**https://dafahaha.github.io/transit-truth/**

#### 手动配置

1. 打开仓库 Settings → Pages
2. Source 选择 "Deploy from a branch"
3. Branch 选择 "main"，目录选择 "/ (root)"
4. 点击 Save
5. 等待 1-2 分钟，站点即可访问

---

## 本地运行

### 纯前端版本（零安装）

**最简单的方式，不需要安装任何东西！**

1. 下载 `index.html` 文件（55KB）
2. 双击用浏览器打开
3. 输入 API Key，开始审计

**所有功能纯前端实现，不需要后端服务器，不需要网络连接（除了调用API）。**

---

### 完整后端版本

如果你需要使用完整功能（数据库、API、贡献系统等），可以本地运行后端。

#### 环境要求

- Python 3.10+
- pip

#### 安装和运行

```bash
# 1. 克隆仓库
git clone https://github.com/dafahaha/transit-truth.git
cd transit-truth

# 2. 安装依赖
cd backend
pip install -r requirements.txt

# 3. 运行
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. 打开浏览器
# http://localhost:8000
```

#### CLI 工具

```bash
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

### Docker 部署

#### 使用 docker-compose

```bash
# 1. 克隆仓库
git clone https://github.com/dafahaha/transit-truth.git
cd transit-truth

# 2. 启动
docker-compose up -d

# 3. 访问
# http://localhost:8000
```

#### 使用 Docker 直接运行

```bash
# 构建镜像
docker build -t transit-truth .

# 运行容器
docker run -d -p 8000:8000 --name transit-truth transit-truth

# 查看日志
docker logs -f transit-truth
```

---

## 国内访问优化

### 问题

GitHub Pages 在国内访问可能不稳定，速度较慢。

### 解决方案

#### 方案1：使用 Vercel（推荐）

Vercel 在全球有 CDN 节点，国内访问速度良好。

- 部署方式：见上方 [Vercel 部署](#vercel国内可访问)
- 访问速度：⭐⭐⭐⭐（国内大部分地区可正常访问）

#### 方案2：使用 Netlify

Netlify 也是全球 CDN，国内访问速度尚可。

- 部署方式：见上方 [Netlify 部署](#netlify)
- 访问速度：⭐⭐⭐

#### 方案3：使用 Gitee Pages

Gitee 是国内的代码托管平台，访问速度快。

1. 注册 Gitee 账号：https://gitee.com
2. Fork 本项目到 Gitee
3. 开启 Gitee Pages：仓库 → 服务 → Gitee Pages
4. 访问地址：`https://你的用户名.gitee.io/transit-truth/`

- 访问速度：⭐⭐⭐⭐⭐（国内最快）
- 注意：Gitee Pages 需要实名认证

#### 方案4：离线版本

下载 `index.html` 文件，本地双击打开，完全不需要网络。

- 访问速度：⭐⭐⭐⭐⭐（本地运行，最快）
- 适用场景：没有稳定网络连接的用户

---

## 自定义域名

### Vercel 自定义域名

1. 打开 Vercel 项目设置 → Domains
2. 输入你的域名，点击 Add
3. 按照提示配置 DNS 解析
4. 等待 DNS 生效（通常几分钟到几小时）

### GitHub Pages 自定义域名

1. 打开仓库 Settings → Pages
2. 在 Custom domain 中输入你的域名
3. 点击 Save
4. 配置 DNS 解析（CNAME 记录指向 `你的用户名.github.io`）
5. 勾选 Enforce HTTPS

---

## 常见问题

### Q: 部署后访问显示 404？

A: 请检查：
1. 部署目录是否正确（应该是根目录）
2. `index.html` 文件是否存在
3. 部署是否完成（通常需要 1-2 分钟）

### Q: 国内访问 GitHub Pages 很慢？

A: 建议使用 Vercel 或 Gitee Pages 部署，国内访问速度更好。详见 [国内访问优化](#国内访问优化)。

### Q: 纯前端版本和完整后端版本有什么区别？

A:

| 功能 | 纯前端版本 | 完整后端版本 |
|---|---|---|
| 模型审计 | ✅ | ✅ |
| 行为指纹 | ✅ | ✅ |
| Token 审计 | ✅ | ✅ |
| 延迟/协议检查 | ✅ | ✅ |
| 余额查询 | ✅ | ✅ |
| 分享卡片 | ✅ | ✅ |
| 数据库存储 | ❌ | ✅ |
| 贡献系统 | ❌ | ✅ |
| 排行榜 | ❌ | ✅ |
| 持续监控 | ❌ | ✅ |
| API 接口 | ❌ | ✅ |

### Q: 部署需要付费吗？

A: 不需要！所有推荐的部署方式都有免费额度：
- Vercel：免费 100GB 带宽/月
- Netlify：免费 100GB 带宽/月
- GitHub Pages：免费（公开仓库）
- Gitee Pages：免费（需要实名认证）

### Q: 如何更新部署？

A:
- Vercel/Netlify：GitHub 推送后自动更新
- GitHub Pages：GitHub 推送后自动更新（1-2分钟）
- 本地运行：重新 `git pull`，然后重启服务
- Docker：重新构建镜像，重启容器

---

## 技术支持

如果部署过程中遇到问题，可以：

1. 查看 [GitHub Issues](https://github.com/dafahaha/transit-truth/issues) 是否有类似问题
2. 提交新的 Issue，详细描述你的问题和环境
3. 查看 [文档](https://github.com/dafahaha/transit-truth#readme)

---

*本文档持续更新中。如果你有更好的部署方式，欢迎提交 PR 改进本文档！*
