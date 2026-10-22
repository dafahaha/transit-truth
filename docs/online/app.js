/* TransitTruth online check — zero-dependency vanilla JS.
 *
 * Security contract (see docs/audit_round1_1022.md and the fresh security review):
 * - Every attacker-controlled string (URL, model id, relay response, error text)
 *   reaches the DOM through textContent / createElement only. innerHTML is never
 *   used with user or relay data.
 * - The API key lives in a plain local variable for the duration of one run. It
 *   is never written to localStorage/sessionStorage, never put in the URL, never
 *   copied into the evidence JSON, never printed.
 * - No server relay: fetches go straight from the browser to the URL the user typed.
 */
(function () {
  'use strict';

  // ─── DOM handles ───
  const form = document.getElementById('verify-form');
  const baseInput = document.getElementById('base-url');
  const modelInput = document.getElementById('claimed-model');
  const keyInput = document.getElementById('api-key');
  const allowPrivate = document.getElementById('allow-private');
  const verifyBtn = document.getElementById('verify-btn');
  const resetBtn = document.getElementById('reset-btn');
  const progressCard = document.getElementById('progress-card');
  const progressList = document.getElementById('progress-list');
  const reportCard = document.getElementById('report-card');
  const verdictBanner = document.getElementById('verdict-banner');
  const reportBody = document.getElementById('report-body');
  const evidencePre = document.getElementById('evidence-pre');
  const corsCard = document.getElementById('cors-card');
  const corsText = document.getElementById('cors-text');
  const copyBtn = document.getElementById('copy-btn');
  const rerunBtn = document.getElementById('rerun-btn');

  const REQUEST_TIMEOUT_MS = 20000;
  const MAX_RAW_SNIPPET = 2000;

  // In-memory only; reset at the end of every run. Never persisted.
  let runKey = null;

  // ─── tiny DOM helper (textContent only) ───
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // ─── URL validation ───
  function parseAndValidate(raw) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) return { ok: false, code: 'invalid_endpoint', reason: 'Base URL 为空。' };
    let url;
    try {
      url = new URL(trimmed);
    } catch (_e) {
      return { ok: false, code: 'invalid_endpoint', reason: 'URL 无法解析：' + trimmed };
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return { ok: false, code: 'invalid_endpoint', reason: '仅支持 http:// 与 https://，拒绝 ' + url.protocol };
    }
    if (!url.hostname) {
      return { ok: false, code: 'invalid_endpoint', reason: 'URL 缺少主机名。' };
    }
    return { ok: true, url };
  }

  function isPrivateHost(hostname) {
    const h = hostname.toLowerCase();
    if (h === 'localhost' || h.endsWith('.localhost') || h === '0.0.0.0') return true;
    // IPv4 literal
    const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (v4) {
      const o = v4.slice(1).map(Number);
      if (o.some((n) => n > 255)) return true;
      if (o[0] === 127) return true;                 // loopback 127.0.0.0/8
      if (o[0] === 10) return true;                  // RFC1918
      if (o[0] === 172 && o[1] >= 16 && o[1] <= 31) return true;
      if (o[0] === 192 && o[1] === 168) return true;
      if (o[0] === 169 && o[1] === 254) return true; // link-local / metadata
      if (o[0] === 100 && o[1] >= 64 && o[1] <= 127) return true; // CGNAT
      return false;
    }
    // IPv6 literal (strip brackets already done by URL parser)
    if (h === '::1') return true;
    if (h.startsWith('fe80')) return true;           // link-local
    if (h.startsWith('fc') || h.startsWith('fd')) return true; // ULA
    return false;
  }

  // Build candidate API roots: typed URL, and /v1 fallback when absent.
  function candidateRoots(url) {
    const base = url.origin + url.pathname.replace(/\/+$/, '');
    const roots = [base];
    if (!/\/v1$/i.test(base)) roots.push(base + '/v1');
    return roots;
  }

  // ─── fetch wrapper with timeout + error classification ───
  async function guardedFetch(resource, options) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const resp = await fetch(resource, Object.assign({ signal: controller.signal }, options));
      return { ok: true, response: resp };
    } catch (e) {
      if (e && e.name === 'AbortError') {
        return { ok: false, kind: 'timeout' };
      }
      // TypeError from fetch = CORS block / DNS failure / offline. We cannot
      // distinguish CORS from DNS here; report honestly as cors_or_network.
      return { ok: false, kind: 'fetch_failed', error: e };
    } finally {
      clearTimeout(timer);
    }
  }

  function authHeaders() {
    const headers = { 'Accept': 'application/json' };
    if (runKey) headers['Authorization'] = 'Bearer ' + runKey;
    return headers;
  }

  // ─── capability sanity (weak liveness, NOT a fingerprint) ───
  const CAPABILITY_QS = [
    {
      id: 'cap-math',
      question: 'What is 7 multiplied by 8? Reply with only the resulting number.',
      match: /\b56\b/,
      label: '基础算术（7×8）',
    },
    {
      id: 'cap-capital',
      question: 'What is the capital city of France? Reply with only the city name.',
      match: /paris/i,
      label: '常识问答（法国首都）',
    },
  ];

  function normalizeAnswer(text) {
    return String(text || '').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  // ─── progress helpers ───
  let steps = [];
  function startProgress() {
    clear(progressList);
    steps = [];
    progressCard.classList.remove('hidden');
  }
  function addStep(text) {
    const li = el('li', '');
    const dot = el('span', 'dot', '•');
    li.appendChild(dot);
    li.appendChild(el('span', '', text));
    progressList.appendChild(li);
    steps.push(li);
    return li;
  }
  function markStep(li, state) {
    li.classList.remove('active', 'done');
    if (state === 'done') li.classList.add('done');
    if (state === 'active') li.classList.add('active');
  }

  // ─── main flow ───
  async function run() {
    reportCard.classList.add('hidden');
    corsCard.classList.add('hidden');
    clear(verdictBanner);
    clear(reportBody);
    clear(evidencePre);

    const parsed = parseAndValidate(baseInput.value);
    if (!parsed.ok) {
      showErrorState('invalid_endpoint', parsed.reason, null);
      return;
    }
    const url = parsed.url;
    if (isPrivateHost(url.hostname) && !allowPrivate.checked) {
      showBlockedPrivate(url.hostname);
      return;
    }

    runKey = keyInput.value ? String(keyInput.value) : null;
    const claimed = modelInput.value.trim();
    const roots = candidateRoots(url);

    verifyBtn.disabled = true;
    startProgress();

    const evidence = {
      checked_at: new Date().toISOString(),
      target_origin: url.origin,
      target_path: url.pathname,
      claimed_model: claimed || null,
      steps: [],
      declared_models: null,
      chat: null,
      capability: [],
    };

    try {
      // 1) GET /models
      const sModels = addStep('读取模型清单 GET /models…');
      markStep(sModels, 'active');
      const modelsProbe = await probeModels(roots, evidence);
      markStep(sModels, 'done');
      if (modelsProbe.halt) {
        handleProbeFailure(modelsProbe, evidence);
        finish();
        return;
      }

      // 2) chat smoke + capability (only when a key is present; without a key
      //    most relays reject chat, so we stop at reachability)
      let chatModel = claimed || (evidence.declared_models && evidence.declared_models[0]) || null;
      if (!runKey) {
        evidence.steps.push({ id: 'no_key', note: '未提供 Key：跳过 chat 探针与能力问答，仅完成可达性/协议体检。' });
        showInsufficient(evidence, '未提供 Key，无法发起 chat 探针；当前证据不足以判定。');
        finish();
        return;
      }

      const sChat = addStep('最小 chat/completions 握手（temperature=0）…');
      markStep(sChat, 'active');
      const chat = await probeChat(roots, chatModel, evidence);
      markStep(sChat, 'done');
      if (chat.halt) {
        handleProbeFailure(chat, evidence);
        finish();
        return;
      }

      // 3) capability sanity
      const sCap = addStep('基础能力快检（弱信号，非指纹）…');
      markStep(sCap, 'active');
      const capResults = await runCapability(roots, chatModel);
      evidence.capability = capResults;
      markStep(sCap, 'done');

      // ─── verdict (browser build never emits pass) ───
      const fails = capResults.filter((c) => !c.passed).length;
      if (fails === capResults.length && capResults.length > 0) {
        showSuspicious(evidence, '两个基础能力问题均未通过：表面能力异常（弱信号，必须用本地 CLI 行为指纹复核，本页不下最终结论）。');
      } else {
        showInsufficient(evidence, '端点可达、协议基本正常；浏览器版无行为参考分布，证据不足以判定真伪（不会签发 pass）。');
      }
    } catch (e) {
      evidence.steps.push({ id: 'unexpected', note: String((e && e.message) || e) });
      showErrorState('transport_error', '体检过程中出现未预期错误：' + String((e && e.message) || e), evidence);
    }
    finish();
  }

  async function probeModels(roots, evidence) {
    let last = null;
    for (const root of roots) {
      const r = await guardedFetch(root + '/models', { headers: authHeaders() });
      if (!r.ok) { last = r; continue; }
      const resp = r.response;
      if (resp.status === 401 || resp.status === 403) {
        return { halt: true, kind: 'auth', status: resp.status, root };
      }
      if (resp.status !== 200) { last = r; continue; }
      let body;
      try { body = await resp.json(); } catch (_e) { last = r; continue; }
      const list = Array.isArray(body && body.data) ? body.data : [];
      evidence.declared_models = list.map((m) => (m && (m.id || m.name)) || String(m)).filter(Boolean);
      evidence.steps.push({ id: 'models', root: root + '/models', status: resp.status, count: evidence.declared_models.length });
      return { halt: false, root, response: resp, body };
    }
    return { halt: true, kind: last && last.kind === 'fetch_failed' ? 'cors' : 'http', last };
  }

  async function probeChat(roots, model, evidence) {
    let last = null;
    for (const root of roots) {
      const payload = {
        model: model || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: 'Reply with exactly the single word: OK' }],
        temperature: 0,
        max_tokens: 8,
        stream: false,
      };
      const r = await guardedFetch(root + '/chat/completions', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
        body: JSON.stringify(payload),
      });
      if (!r.ok) { last = r; continue; }
      const resp = r.response;
      if (resp.status === 401 || resp.status === 403) {
        return { halt: true, kind: 'auth', status: resp.status, root };
      }
      if (resp.status !== 200) { last = r; continue; }
      let body;
      try { body = await resp.json(); } catch (_e) { last = r; continue; }
      const choice = body && body.choices && body.choices[0];
      const content = choice && choice.message && choice.message.content;
      evidence.chat = {
        root: root + '/chat/completions',
        status: resp.status,
        echo_model: body && body.model ? String(body.model) : null,
        system_fingerprint: body && body.system_fingerprint ? String(body.system_fingerprint) : null,
        has_usage: !!(body && body.usage),
        has_choices: !!choice,
        content_preview: content ? String(content).slice(0, MAX_RAW_SNIPPET) : null,
      };
      return { halt: false, root, response: resp, body };
    }
    return { halt: true, kind: last && last.kind === 'fetch_failed' ? 'cors' : 'http', last };
  }

  async function runCapability(roots, model) {
    const results = [];
    for (const q of CAPABILITY_QS) {
      let passed = false;
      let answer = null;
      let status = null;
      for (const root of roots) {
        const payload = {
          model: model || 'gpt-3.5-turbo',
          messages: [{ role: 'user', content: q.question }],
          temperature: 0,
          max_tokens: 16,
          stream: false,
        };
        const r = await guardedFetch(root + '/chat/completions', {
          method: 'POST',
          headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
          body: JSON.stringify(payload),
        });
        if (!r.ok || r.response.status !== 200) continue;
        status = r.response.status;
        let body;
        try { body = await r.response.json(); } catch (_e) { continue; }
        const choice = body && body.choices && body.choices[0];
        answer = choice && choice.message && choice.message.content;
        passed = q.match.test(normalizeAnswer(answer));
        break;
      }
      results.push({ id: q.id, label: q.label, passed, answer: answer ? String(answer).slice(0, 300) : null, status });
    }
    return results;
  }

  function handleProbeFailure(probe, evidence) {
    if (probe.kind === 'auth') {
      showErrorState('missing_api_key',
        '端点返回 ' + probe.status + '：Key 缺失或被拒。请换一个该端点认可的临时 Key 重试；本页不判断 Key 本身是否正确。',
        evidence);
      return;
    }
    if (probe.kind === 'cors') {
      showCorsBlocked(evidence);
      return;
    }
    if (probe.last && probe.last.kind === 'timeout') {
      showErrorState('transport_error', '请求超时（' + REQUEST_TIMEOUT_MS / 1000 + 's）：端点无响应或网络不通。', evidence);
      return;
    }
    showErrorState('transport_error', '所有候选路径均未返回可用响应（HTTP ' +
      (probe.last && probe.last.response ? probe.last.response.status : '?') + '）。', evidence);
  }

  // ─── renderers ───
  function banner(kind, word, sub) {
    clear(verdictBanner);
    const box = el('div', 'verdict-banner verdict-' + kind);
    box.appendChild(el('div', 'v-word', word));
    box.appendChild(el('div', 'v-sub', sub));
    verdictBanner.appendChild(box);
  }

  function checkRow(iconKind, name, detail) {
    const row = el('div', 'check-row');
    row.appendChild(el('div', 'ic ic-' + iconKind, iconKind === 'ok' ? '✓' : iconKind === 'bad' ? '✗' : iconKind === 'warn' ? '!' : 'i'));
    const body = el('div', 'body');
    body.appendChild(el('div', 'name', name));
    if (detail) body.appendChild(el('div', 'detail', detail));
    row.appendChild(body);
    return row;
  }

  function showInsufficient(evidence, summary) {
    reportCard.classList.remove('hidden');
    banner('insufficient', 'insufficient_evidence · 证据不足', summary);
    renderCommon(evidence, 'info');
    reportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showSuspicious(evidence, summary) {
    reportCard.classList.remove('hidden');
    banner('suspicious', 'suspicious · 表面异常（弱信号）', summary);
    renderCommon(evidence, 'warn');
    reportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showErrorState(code, reason, evidence) {
    reportCard.classList.remove('hidden');
    const label = {
      invalid_endpoint: 'invalid_endpoint · 地址无效',
      transport_error: 'transport_error · 传输错误',
      missing_api_key: 'missing_api_key / auth · Key 缺失或被拒',
    }[code] || code;
    banner('error', label, reason);
    if (evidence) renderCommon(evidence, 'bad');
    reportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showBlockedPrivate(hostname) {
    reportCard.classList.remove('hidden');
    banner('error', 'blocked_private · 内网/本机地址已拦截',
      '默认拦截 ' + hostname + '（loopback / RFC1918 / 链路本地 / CGNAT）。确认你在测自己的本机网关后，勾选"我知道我在测本机/内网网关"再放行。');
    const section = el('div', 'report-section');
    section.appendChild(el('h3', '', '为什么默认拦截'));
    section.appendChild(el('p', 'muted', '浏览器直连内网地址可能把本机/内网服务暴露给页面脚本；本地网关开发者属真实用户，故提供知情勾选放行。'));
    reportBody.appendChild(section);
    reportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showCorsBlocked(evidence) {
    corsCard.classList.remove('hidden');
    if (evidence) renderEvidence(evidence);
    clear(corsText);
    corsText.textContent = '浏览器未能读取该端点响应（CORS 未放行或网络不可达）。这是浏览器同源策略的正常边界，不是你的 Key 出错。';
    corsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function renderCommon(evidence, defaultIcon) {
    clear(reportBody);

    if (evidence.declared_models && evidence.declared_models.length) {
      const sec = el('div', 'report-section');
      sec.appendChild(el('h3', '', '声明模型清单（GET /models，共 ' + evidence.declared_models.length + ' 个）'));
      const chips = el('div', 'chip-list');
      evidence.declared_models.forEach((m) => {
        const chip = el('span', 'chip' + (evidence.claimed_model && m.toLowerCase() === evidence.claimed_model.toLowerCase() ? ' chip-claimed' : ''), m);
        chips.appendChild(chip);
      });
      sec.appendChild(chips);
      if (evidence.claimed_model) {
        const hit = evidence.declared_models.some((m) => m.toLowerCase() === evidence.claimed_model.toLowerCase());
        sec.appendChild(checkRow(hit ? 'ok' : 'info',
          '声称模型匹配',
          hit ? '声称模型出现在声明清单中（仅清单层面，不代表真身）。' : '声称模型未在清单中出现（中转站常做别名，需 CLI 复核）。'));
      }
      reportBody.appendChild(sec);
    }

    if (evidence.chat) {
      const sec = el('div', 'report-section');
      sec.appendChild(el('h3', '', 'chat 协议结构'));
      const c = evidence.chat;
      sec.appendChild(checkRow(c.has_choices ? 'ok' : 'bad', 'choices[0].message 结构', c.has_choices ? '正常返回 OpenAI 兼容结构。' : '缺少 choices[0].message。'));
      sec.appendChild(checkRow(c.has_usage ? 'ok' : 'info', 'usage 计量字段', c.has_usage ? '返回 usage。' : '未返回 usage（部分中转省略，单独不构成问题）。'));
      sec.appendChild(checkRow('info', '模型回显 / system_fingerprint',
        'echo=' + (c.echo_model || '（无）') + ' · fingerprint=' + (c.system_fingerprint || '（无）')));
      if (c.content_preview) {
        sec.appendChild(checkRow('info', '回复片段（已截断，纯文本展示）', c.content_preview));
      }
      reportBody.appendChild(sec);
    }

    if (evidence.capability && evidence.capability.length) {
      const sec = el('div', 'report-section');
      sec.appendChild(el('h3', '', '基础能力快检（弱信号，非模型指纹）'));
      evidence.capability.forEach((c) => {
        sec.appendChild(checkRow(c.passed ? 'ok' : 'bad', c.label,
          '回答：' + (c.answer || '（无响应）') + (c.status ? ' · HTTP ' + c.status : '')));
      });
      reportBody.appendChild(sec);
    }

    renderEvidence(evidence);
  }

  function renderEvidence(evidence) {
    // Key 绝不进入 evidence；此处序列化的对象里也没有 key 字段。
    evidencePre.textContent = JSON.stringify(evidence, null, 2);
  }

  // ─── finish / reset ───
  function finish() {
    runKey = null;
    keyInput.value = '';
    verifyBtn.disabled = false;
  }

  function resetAll() {
    form.reset();
    runKey = null;
    reportCard.classList.add('hidden');
    corsCard.classList.add('hidden');
    progressCard.classList.add('hidden');
    clear(verdictBanner);
    clear(reportBody);
    clear(evidencePre);
  }

  copyBtn.addEventListener('click', () => {
    const text = evidencePre.textContent || '';
    if (!text) return;
    navigator.clipboard.writeText('TransitTruth 在线体检报告\n' + text).then(
      () => { copyBtn.textContent = '已复制 ✓'; setTimeout(() => { copyBtn.textContent = '复制报告文本'; }, 1500); },
      () => { copyBtn.textContent = '复制失败，请手动选择'; }
    );
  });

  rerunBtn.addEventListener('click', () => { run(); });
  resetBtn.addEventListener('click', resetAll);

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    run();
  });

  // Expose pure predicates only (never the key) for headless self-tests.
  window.TT = {
    isPrivateHost: isPrivateHost,
    parseAndValidate: parseAndValidate,
    candidateRoots: candidateRoots,
    normalizeAnswer: normalizeAnswer,
  };

  // Read-only deep-link prefill (?url=, ?model=, ?auto=1). The API key is
  // NEVER accepted from the query string — it can only be typed into the field
  // and held in memory.
  (function initFromQuery() {
    const q = new URLSearchParams(location.search);
    const u = q.get('url');
    const m = q.get('model');
    if (u) baseInput.value = u;
    if (m) modelInput.value = m;
    // Self-test / local-gateway deep link only; the checkbox remains visible and
    // unchecked by default for normal users.
    if (q.get('private') === '1') allowPrivate.checked = true;
    // Local-only key injection for headless self-test / screenshots. On any
    // non-loopback origin (including the published Pages site) the ?key=
    // parameter is ignored entirely; the key can never arrive via URL in
    // production.
    const host = location.hostname;
    if ((host === 'localhost' || host === '127.0.0.1') && q.get('key')) {
      keyInput.value = q.get('key');
    }
    if (q.get('details') === '1') {
      const d = document.querySelector('details.evidence');
      if (d) d.open = true;
    }
    if (q.get('auto') === '1' && u) {
      // Defer so the page paints before the async run starts.
      setTimeout(run, 120);
    }
  })();
})();
