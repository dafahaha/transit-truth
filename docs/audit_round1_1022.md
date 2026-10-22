# TransitTruth 全新代码安全审查报告 · Round 1（2026-10-22）

- 审查基线：`70b64ee` "Release v0.5.9"，本地 == 远程，工作树初始干净。
- 审查人：全新视角复核（不预设前序轮次结论正确），覆盖正确性、安全、测试有效性（变异法）。
- 执行环境：Windows + Python 3.13.16（`.venv-win`），git over SSH。
- 结论摘要：**未发现需要修复的 P0/P1/P2 真实缺陷**；关键安全/判定不变量经变异实验全部被测试捕获。本轮除阶段 0 清理与本报告外，未改动业务代码。

## 1. 基线测试实数（全新跑取，非引用旧值）

命令：`python -m pytest --tb=short -q`（`.venv-win`）

- **352 passed, 7 skipped**（0 failed, 0 error）。
- 测试文件：36 个（`backend/tests/test_*.py`）。
- `python -m compileall -q app`：全部模块语法编译通过。

### 平台性说明（非代码缺陷，已在 pristine 环境复现）

首次直接跑 pytest 时，`tiktoken` 的 `o200k_base` BPE 需从 `openaipublic.blob.core.windows.net` 下载，本机直连被拒（WinError 10061，Python 默认不走系统代理 `127.0.0.1:7890`）。经系统代理预热一次后，BPE 落入 tiktoken 本地缓存，后续**无代理离线复跑成功**。GitHub Actions CI 自带网络，不受影响。此为本机环境问题，未改代码、未改依赖。

## 2. 审查范围与方法

1. 通读 verify 判定链：`verify/core.py`（三态判定/硬顶/弱 pass 封顶/tokenizer 覆盖）、`verify/battery.py`（探针执行/样本预算）、`verify/reference.py`（tokenizer 一致性）、`verify/report.py`（报告组装）、`verify/serve.py`（本地服务/CSP/净化/Origin/Host 校验）、`core/statistical_analyzer.py`（KS/卡方/贝叶斯/LR）、`utils/ssrf_guard.py`（URL 层 + 连接层防 rebinding）、`utils/http_client.py`、`api/*`（audit/contribute/balance/ranking/detect）、`database.py`（SQL 参数化）、`moderation.py`、`core/balance_checker.py`、`core/retry.py`、`config.py`、`verify/otel.py`。
2. 安全模式扫描：`shell=True/eval/exec/pickle/verify=False/subprocess/os.system/yaml.load/innerHTML` 全仓 0 命中；SQL 全部参数化；未发现 api_key 进入日志/响应/OTel 属性。
3. 变异法（mutation testing）验证关键测试有效性：对源码做最小突变 → 跑定向测试 → 期望失败（CAUGHT）→ 还原。完整记录见第 4 节。

## 3. 发现分级

### P0（可直接利用/崩溃/泄露）

无。

### P1（安全绕过/错误认证/资金与隐私泄露）

无。

### P2（边界错误导致误判/错误结果）

无。逐条复核过的高风险面均正确：

| 面 | 文件:行 | 复核结论 |
|---|---|---|
| 非公开 URL 拒绝（loopback/私网/链路本地/CGNAT/保留地址） | `utils/ssrf_guard.py:61-82, 98-131` | URL 层解析 + DNS 逐条记录检查；`_is_blocked_ip` fail-closed（不可解析→拦截） |
| DNS rebinding 连接层回读 peer | `utils/ssrf_guard.py:175-219` | 建连后回读真实 peer，非公开则关闭流并抛 ConnectError；peer 未知 fail-closed |
| 密钥不回显/不落盘/不进日志 | `verify/core.py:216-227`、`verify/serve.py` `sanitize_report`、`verify/otel.py:26-47` | 缺 key 返回 missing_api_key；报告递归净化敏感键；OTel 只放 host 不含 userinfo |
| CORS | `main.py:30-33`、`serve.py` | `allow_credentials=False`，无 `*` 通配凭证；本地服务校验 Origin/Host |
| 三态硬顶（tokenizer-only 参考不得出 pass） | `verify/core.py` `_apply_hard_cap` | 分支 A/B 分别覆盖，pass 被降级 insufficient_evidence |
| tokenizer 跨族不一致升级 suspicious 并清空行为数字 | `verify/core.py` tokenizer override 段 | 已由 v046/v055 测试锁定 |
| 空行为证据不得 x3.0 奖励、posterior/LR/CI 置 null | `core/statistical_analyzer.py:683-714, 775` | has_behavioral_evidence 门控，空数据 sentinel p=1.0 不被读作 match |
| 公共排行榜写入需人工审批单事务 | `database.py:295-320`、`moderation.py:108-124` | 匿名 contribute 不写榜；upsert + 状态翻转同一事务，失败回滚 |
| 自定义端点 host 改写防护（单次解码后拒 `// @ # \`） | `core/balance_checker.py:validate_custom_endpoint` | 双重编码无法二次解码到控制符 |

### P3（观察项，本轮不修，记录在案）

- **O1（P3，资源）**：`utils/rate_limit.py` 的 `_windows` 字典按客户端 IP 累积，未清理过期窗口；长驻公网部署会缓慢增长。默认 loopback 本地工具影响小，未改。
- **O2（P3，测试深度）**：bundled webapp 的 `esc()` 转义由静态源码扫描 + root/bundled 哈希一致性测试覆盖，未对敌对字符串做运行时执行断言；当前所有插值点均经 `esc()`/白名单，残余风险低。
- **O3（P3，环境）**：tokenizer 探针依赖 tiktoken 离线缓存；全新环境首跑需联网一次（见第 1 节平台说明）。
- **O4（设计边界，非缺陷）**：浏览器环境无法运行 tiktoken BPE 计数，在线工具（Round 1 阶段 2）按设计**省略 tokenizer 探针**，不得据此宣称 pass。

## 4. 变异实验记录（变异 → 定向测试 → 结果）

方法：临时把源码改为"错误版本"，跑对应测试；测试失败=CAUGHT（测试有效），通过=ALIVE（测试未拦截，需说明）。每次实验后立即还原，结束后 `git diff` 确认源码零残留。

| # | 变异位置 | 变异内容 | 定向测试 | 结果 |
|---|---|---|---|---|
| M1 | `verify/core.py` `_apply_hard_cap` | 删除 pass→insufficient_evidence 降级 | `test_v057_hardcap_branches.py::test_branch_a_pass_is_downgraded_to_insufficient_evidence` | **CAUGHT**（断言 pass≠insufficient_evidence） |
| M2 | `verify/core.py` tokenizer mismatch override | 关闭跨族不一致升级 | `test_v055_hardcap_consistency.py::test_tokenizer_mismatch_suspicious_reason_not_family_consistent` | **CAUGHT**（pass 应为 suspicious） |
| M3 | `verify/serve.py` `sanitize_report` | 保留敏感键不剔除 | `test_serve.py::test_sanitize_report_strips_and_redacts` | **CAUGHT**（api_key 仍在报告里） |
| M4a | `utils/ssrf_guard.py` scheme 检查 | 关闭 http/https scheme 门控 | `test_verify_hardening.py::test_unknown_protocol_rejected`（ftp://） | **CAUGHT**（误报 no_observations 而非 invalid_endpoint） |
| M4b | `utils/ssrf_guard.py` connect_tcp peer 块 | 关闭连接层 peer 拦截 | `test_security_round2.py::test_guarded_backend_blocks_loopback_peer` | **CAUGHT**（未抛 ConnectError） |
| M5 | `verify/webapp/index.html` ESC_MAP | 删除 `<` 转义 | `test_webapp_esc_static.py` 全文件 | **CAUGHT**（bundled/root 哈希一致性测试失败；注：非运行时语义断言，见 O2） |
| M6 | `main.py` CORS | `allow_credentials=False→True` | `test_api_security.py::test_cors_credentials_disabled` | **CAUGHT** |
| M7 | `verify/core.py` 缺 key 早返回 | 关闭 missing_api_key 分支 | `test_verify.py::test_missing_key_is_insufficient_evidence` | **CAUGHT**（无 key 竟走到 pass） |

**ALIVE 说明（非漏洞）**：首轮把 M4 的 `ip.is_loopback` 单独删除时测试未失败——因 `is_private` 在 Python `ipaddress` 中同样覆盖 127.0.0.0/8，属防御重叠；把 M4a 对准带 host 的 ftp 路径、M4b 对准 connect peer 后均 CAUGHT。无"测试测不到的真实漏洞"残留。

## 5. 数据资产实数（供在线工具与文档引用，不夸大）

- 真实基线：2 个——`gpt-4o`（n=50，8 行为探针 / 8 tokenizer 探针）、`gpt-4o-mini`（n=50，8 行为 / 5 tokenizer），位于 `data/baselines/`。
- 开放指纹：2 个，均为 **tokenizer-only、无行为分布**——`qwen2.5-0.5b-instruct`（real）、`deepseek-r1-distill-qwen-1.5b`（derived，与 Qwen 同 tokenizer，二者 tokenizer 不可区分）。
- 行为参考仅存在于 2 个 GPT 基线；浏览器单轮小样本不具备复现统计检验的条件。

## 6. 修复清单

本轮无业务代码修复（无 P0/P1/P2）。阶段 0 的清理（删除 `.triage_backup/`、`.gitignore` 增补 `.triage_backup/`、`*.wt`、`.r2_pytest_tmp.txt`）见提交记录。

## 7. 给后续"全新安全审查代理"的重点位置（后端侧）

1. `verify/serve.py` 的 Origin/Host/Content-Type 校验与 CSP（inline script 是必需的，检查是否有可去掉的 unsafe-inline）。
2. `utils/ssrf_guard.py` connect_tcp 的 peer 回读：`_peer_ip` 对 httpcore 版本漂移的形状假设，以及 `is None` fail-closed 分支。
3. `verify/core.py` tokenizer override 与硬顶的交互顺序（先 override 还是先 cap）。
4. `moderation.py` `_build_ranking_entry` 的类型 coercion 是否会把污染字符串写进公共榜。
5. `utils/rate_limit.py` 窗口字典的过期回收（O1）。

---

## 8. 阶段 2/4：纯静态在线工具（`docs/online/`）构建与自测证据

### 8.1 形态与文件清单（零构建、无 CDN、无框架）

- `docs/online/index.html` — 页面 + 收紧 CSP meta（`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https: http:; base-uri 'self'; form-action 'none'`；无 `unsafe-inline` 脚本、无外部 script src）。
- `docs/online/styles.css` — 苹果风，主色 `#0071e3`，无紫/靛；移动优先，640px 断点单列转双列。
- `docs/online/app.js` — 原生 IIFE，无依赖；纯函数挂 `window.TT` 仅供 headless 自测。
- 新增离线静态守卫：`backend/tests/test_online_tool_static.py`（11 例，CI 可跑，无需浏览器/网络）。

### 8.2 浏览器可复现 / 不可复现的探测划分（诚实）

- **浏览器做**：`GET /models` 声明清单比对；最小 chat/completions（temperature=0, max_tokens=8）协议结构检查（choices[0].message、usage、echo model、system_fingerprint）；2 道普适常识弱信号快检（7×8、法国首都），仅在双双失败时给 `suspicious` 弱提示。
- **浏览器不做（明确跳过并在页面说明）**：tiktoken BPE tokenizer 计数、行为分布卡方/KS/贝叶斯后验——浏览器无参考分布、无法跑 tiktoken；**在线版永不签发 `pass`**。
- 状态机：`pass`（渲染器保留但逻辑不发）/ `suspicious` / `insufficient_evidence` / `transport_error` / `missing_api_key(auth)` / `cors_blocked` / `invalid_endpoint` / `blocked_private`。

### 8.3 安全红线落地

- **XSS**：所有外部来源字符串（URL、模型名、relay 回显、错误文案、原始 JSON）一律 `textContent`/`createElement` 进 DOM；`app.js` 无 `innerHTML/outerHTML/document.write/insertAdjacentHTML`（静态守卫断言）。
- **URL/SSRF**：仅 http/https；拒绝 file:/data:/ftp:/ws:；默认拦截 loopback(127/::1/localhost)、RFC1918(10/8,172.16/12,192.168/16)、链路本地 169.254/16（含 169.254.169.254）、CGNAT 100.64/10、ULA fc/fd、fe80；知情勾选后放行本机/内网网关。注意：浏览器端无法做服务端那种异步 DNS rebinding 回读，域名指向内网的情况靠 CORS/网络失败诚实暴露，不假装拦截。
- **Key**：仅内存变量 `runKey`；不写 localStorage/sessionStorage/cookie、不进 URL query（`?key=` 仅在 127.0.0.1/localhost 自测时读取，发布域忽略）、不进 evidence JSON、不进错误文案；结束即清空输入框。
- **无服务端中转**：Pages 纯静态，fetch 直连用户填写端点；CORS 读不到时给诚实降级卡 + CLI/serve 文档链接。

### 8.4 headless Chrome 自测证据（本地 http.server + 本地 mock 端点）

| 场景 | 输入 | 实测结果 |
| --- | --- | --- |
| 可达 + 声明清单 + chat 结构 | mock good 8800，带本地 dummy key | `insufficient_evidence`（不发 pass）；chips 渲染 gpt-4o-mini/gpt-4o；choices/usage/system_fingerprint 齐；能力答 56/Paris；**DOM/evidence 中 dummy key 出现 0 次** |
| 弱信号双双失败 | mock bad 8801（答 31/London） | `suspicious · 表面异常（弱信号）`，两行 bad 记录回答原文 |
| 401 | mock auth 8802 | `missing_api_key / auth · Key 缺失或被拒`，不判"key 错误" |
| 不可达域名 | `http://nonexistent.invalid/v1` | CORS/网络降级卡显示，非 pass |
| 未带 key | good 8800 无 key | 仅可达性，`insufficient_evidence`，跳过 chat/能力 |
| 内网默认拦截 | `http://127.0.0.1:8800/v1` 不勾选 | `blocked_private`，不发请求 |
| 非法协议 | `ftp://` / `file:///etc/passwd` / `data:text/html,` | `invalid_endpoint · 仅支持 http/https` |
| XSS 注入 | 模型名填 `"><img src=x onerror=alert(1)><script>alert(2)</script>`（含 echo 回显） | DOM 无任何真实 `<img>`/`<script>` 元素，全部转义为文本 |
| 移动视口 | 390px 宽 | 单列堆叠，chips 换行，无横向溢出 |

全量 pytest 复跑：**363 passed, 7 skipped**（基线 352 + 新增在线工具静态守卫 11），后端未受影响。

## 9. 给下一轮"全新安全审查代理"重点攻击位置（在线工具侧）

1. **URL 校验绕过**：`isPrivateHost` 的 IPv4 段判断（八进制/十进制 IP、`0177.0.0.1`、`127.1` 简写、IPv6 映射 v4、`[::ffff:127.0.0.1]`、IDN/Unicode 主机名、`@` userinfo 绕到内网、尾随点 `localhost.`）；`new URL` 之后 hostname 规范化是否全覆盖。
2. **XSS 注入点**：声明模型清单 `data[].id/name`、chat 的 `model` 回显、`system_fingerprint`、usage 数字、错误状态文案、原始 `<pre>` JSON——逐个喂 `<img onerror>`、`javascript:`、实体嵌套、超长字符串。
3. **Key 泄露面**：剪贴板复制内容、evidence 折叠区、网络请求头、报错堆栈、`?key=` 在发布域是否真被忽略、reset/finish 是否清空。
4. **CSP 缺口**：`connect-src https: http:` 为放开任意域（浏览器 CORS 本就独立生效，确认无 unsafe-inline 脚本可注入）；`style-src 'self'` 下页面是否存在内联 style 属性被拦。
5. **CORS 降级文案诚实性**：把 DNS 失败与 CORS 混为一谈是否误导；401/403/429/5xx 分类是否诚实，不把限流说成造假。
6. **弱信号误报**：常识题答案变体（"五十有六"、Paris 大小写/前后缀）是否误判；拒绝回答/空回复是否被错标 suspicious。
