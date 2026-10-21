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
