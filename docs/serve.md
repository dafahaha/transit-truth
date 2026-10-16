# 本地 Web 验真：`transit-truth serve`

把命令行验真包成一个"打开网页就能测"的本地工具：在浏览器里填中转站地址和声称模型，
本地服务端发探针电池，页面直接渲染三态报告。

```bash
transit-truth serve
# 打开 http://127.0.0.1:8766/  （或加 --open 自动开浏览器）
```

## 网络模型（先读这个）

- 浏览器**不能**直连中转端点：浏览器到第三方 OpenAI 兼容接口受 **CORS** 限制，
  且浏览器环境也不该把你的 key 暴露给目标域。真实测试由**本地服务端**在后端发探针，
  页面只是表单 + 报告渲染。
- 因此本工具必须跑在一台**能运行 Python 核验引擎**的机器上（本机或 VPS/容器）。
- 本地服务与 UI **同源**：`webapp/` 静态页和 `/api/verify` 由同一个 uvicorn 进程托管，
  代码**不**发出 `Access-Control-Allow-Origin: *`，别的网页无法驱动这个本地端口。

## Key 安全保证（硬约束）

- API Key 只存在于本次浏览器会话的内存里：**不落盘、不写日志（含 uvicorn access log）、
  不进响应、不进可分享报告**。
- 返回前 `sanitize_report` 做第二道脱敏（defense in depth）：递归剥掉 `api_key /
  authorization / bearer / key` 等字段，并把 `sk-...`、`Bearer ...` 形态的字符串打码，
  即使引擎将来意外带上 key 也不会外泄。
- 报告页顶部明示"本报告不含 key，可安全分享"。
- 默认只监听 `127.0.0.1`（本机回环，局域网都不可达）。

## 命令参数

```
transit-truth serve [--host 127.0.0.1] [--port 8766] [--allow-public]
                    [--allow-local] [--open]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 绑定地址。写 `0.0.0.0` 必须显式带 `--allow-public`，否则拒绝启动 |
| `--port` | `8766` | 监听端口 |
| `--allow-public` | 关 | 允许绑定 `0.0.0.0`；启动时打印醒目风险警告 |
| `--allow-local` | 关 | 放行回环/私网目标，仅用于对接本地参考服务器自测 |
| `--open` | 关 | 启动后自动打开默认浏览器 |

### 公开托管（VPS/自建）的责任

把端口暴露到公网（`--host 0.0.0.0 --allow-public`）会让这台机器**变成任何人都能用的
探针代理**：

- 绝不要在不可信网络上带真实 key 跑公开实例；服务不记 key，但你自己的浏览器会话会。
- 前置反向代理（Caddy/Nginx）做 TLS 和访问控制（Basic Auth / VPN），不要裸奔。
- 容器默认把端口映射回宿主机 `127.0.0.1:8766`，再由反代理接管，见下文 Docker。

## 本地一键脚本

- Windows PowerShell：`scripts/serve.ps1`
- POSIX：`scripts/serve.sh`

两者都默认起 `127.0.0.1:8766`，不带 `--allow-public`。

## Docker（VPS 自用）

`Dockerfile.serve` 只装后端依赖、拷贝 `backend/` 与 `webapp/`，以非 root 运行；compose
服务把容器端口映射到宿主机 `127.0.0.1:8766`（仅本机可达），再由 Caddy/Nginx 加 TLS：

```bash
docker compose -f docker-compose.serve.yml up -d --build
```

Caddy 示例（把 `verify.example.com` 换成你的域名，Caddy 自动签证书）：

```caddy
verify.example.com {
    reverse_proxy 127.0.0.1:8766
}
```

## 部署边界：Cloudflare / 静态 Pages 能做什么、不能做什么

- **Cloudflare Pages / GitHub Pages 只能托管静态门面（介绍、引导、离线 demo）**。
  Workers 运行时是 V8 isolate，**无法运行 Python 核验引擎**（tiktoken、scipy、async
  httpx 电池都跑不起来），所以静态站点不能在线实测中转站。
- 实时后端必须跑在能执行 Python 的地方：本机、VPS、或上面的 Docker 容器。
- 本仓库**没有**提供"纯 JS Worker 代理"；不声称支持，也不伪造。若未来要做一个只转发
  探针、不做统计的薄代理，需另行实现并单独说明其安全边界。

## 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 页面打不开 | 服务没起，或端口被占；换 `--port` |
| `missing_api_key` | 未填 key 且服务端无 `TRANSIT_TRUTH_API_KEY` 环境变量 |
| `invalid_endpoint` / 拒绝回环 | 默认 SSRF 守卫拦截了私网/回环目标；自测本地参考服务器才加 `--allow-local` |
| 连不上 / 超时 | 目标不可达、防火墙或目标拒绝；检查 base_url 是否带 `/v1` |
| `insufficient_evidence` | 证据不足（样本太少/不配合/冷启动），fail-closed 不硬判 pass，不等于"造假" |
| 未知模型 | 声称模型无本地参考目录，无法比对，落 `insufficient_evidence` |
