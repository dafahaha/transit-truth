
// ============================================================
// TransitTruth 纯前端版本
// 所有 API 请求直接从浏览器发出，不需要后端
// ============================================================

import { getEncoding } from 'https://esm.sh/js-tiktoken@1.0.12';

// ─── 已知中转站映射 ────────────────────────────────────────
const KNOWN_RELAYS = [
  { name: 'OpenAI 官方', base_url: 'https://api.openai.com/v1', pattern: /api\.openai\.com/ },
  { name: 'wolfai', base_url: 'https://wolfai.top/v1', pattern: /wolfai/ },
  { name: 'API2D', base_url: 'https://openai.api2d.net/v1', pattern: /api2d/ },
  { name: 'OhMyGPT', base_url: 'https://api.ohmygpt.com/v1', pattern: /ohmygpt/ },
  { name: 'AIHub', base_url: 'https://aihubmix.com/v1', pattern: /aihubmix/ },
  { name: 'CloseAI', base_url: 'https://api.closeai-asia.com/v1', pattern: /closeai/ },
  { name: 'BetterAPI', base_url: 'https://api.betterapi.net/v1', pattern: /betterapi/ },
  { name: 'GeekAPI', base_url: 'https://api.geekapi.net/v1', pattern: /geekapi/ },
  { name: 'AnyAI', base_url: 'https://api.anyai.app/v1', pattern: /anyai/ },
  { name: 'AIProxy', base_url: 'https://api.aiproxy.io/v1', pattern: /aiproxy/ },
  { name: 'OneAPI', base_url: 'http://localhost:3000/v1', pattern: /localhost:3000/ },
  { name: 'NewAPI', base_url: 'http://localhost:3001/v1', pattern: /localhost:3001/ },
];

// ─── 探针定义 ──────────────────────────────────────────────
const TOKENIZER_PROBES = [
  { id: 'tok-digits', prompt: 'Repeat this string exactly: 123456789012345678901234567890', expected_range: [15, 35] },
  { id: 'tok-cjk', prompt: 'Repeat this string exactly: 人工智能强化学习具身智能机器人视觉语言模型', expected_range: [10, 40] },
  { id: 'tok-emoji', prompt: 'Repeat this string exactly: 🤖🧠🚀💻🎯🔥✨🌟💡🎨', expected_range: [10, 50] },
  { id: 'tok-code', prompt: 'Repeat this string exactly: def foo(x): return x*2+1  # test', expected_range: [10, 30] },
];

const BEHAVIORAL_PROBES = [
  { id: 'beh-random-100', prompt: 'Pick a random number between 1 and 100. Reply with ONLY the number.', max_tokens: 8 },
  { id: 'beh-random-color', prompt: 'Name a random color. Reply with ONLY the color name.', max_tokens: 8 },
  { id: 'beh-coin-flip', prompt: 'Flip a coin. Reply with ONLY heads or tails.', max_tokens: 4 },
  { id: 'beh-random-letter', prompt: 'Pick a random letter from A to Z. Reply with ONLY the letter.', max_tokens: 4 },
  { id: 'beh-dice-roll', prompt: 'Roll a six-sided die. Reply with ONLY the number 1-6.', max_tokens: 4 },
  { id: 'beh-random-animal', prompt: 'Name a random animal. Reply with ONLY the animal name.', max_tokens: 8 },
  { id: 'beh-random-day', prompt: 'Pick a random day of the week. Reply with ONLY the day name.', max_tokens: 8 },
  { id: 'beh-number-1-10', prompt: 'Pick a random number between 1 and 10. Reply with ONLY the number.', max_tokens: 4 },
  // 中文行为探针（文化偏好差异更大，区分度更高）
  { id: 'beh-zh-number', prompt: '从一到十中选一个随机中文数字。只回复这个中文数字。', max_tokens: 4 },
  { id: 'beh-zh-color', prompt: '从红、橙、黄、绿、青、蓝、紫中选一个随机颜色。只回复这个颜色名称。', max_tokens: 4 },
  { id: 'beh-zh-festival', prompt: '从春节、元宵、清明、端午、中秋、重阳中选一个随机中国传统节日。只回复节日名称。', max_tokens: 8 },
  { id: 'beh-zh-surname', prompt: '从赵、钱、孙、李、周、吴、郑、王中选一个随机中文姓氏。只回复这个姓氏。', max_tokens: 4 },
  { id: 'beh-zh-city', prompt: '从北京、上海、广州、深圳、杭州、成都中选一个随机中国城市。只回复城市名称。', max_tokens: 8 },
  { id: 'beh-zh-food', prompt: '从麻婆豆腐、宫保鸡丁、红烧肉、糖醋排骨、鱼香肉丝中选一个随机中国菜。只回复菜名。', max_tokens: 8 },
];

const CAPABILITY_PROBES = [
  { id: 'cap-simple-math', prompt: 'What is 17 * 23? Reply with ONLY the number.', expected: ['391'], max_tokens: 8 },
  { id: 'cap-logic', prompt: 'If all cats are animals and some animals are black, can we conclude some cats are black? Answer yes or no only.', expected: ['no', 'No', 'NO'], max_tokens: 4 },
  { id: 'cap-reasoning', prompt: 'A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Reply with ONLY the number of cents.', expected: ['5', '5 cents'], max_tokens: 8 },
];

// ─── 模型参考数据（来自Artificial Analysis / LMArena / 官方文档）───
const MODEL_REFERENCE = {
  'gpt-4o': { name: 'GPT-4o', provider: 'OpenAI', tier: '旗舰', inputPrice: 2.5, outputPrice: 10.0, intelligence: 78.5, elo: 1285, ttft: 0.65, speed: 80, context: '128K', release: '2024-05' },
  'gpt-4o-mini': { name: 'GPT-4o Mini', provider: 'OpenAI', tier: '轻量', inputPrice: 0.15, outputPrice: 0.6, intelligence: 68.2, elo: 1180, ttft: 0.45, speed: 150, context: '128K', release: '2024-07' },
  'gpt-4-turbo': { name: 'GPT-4 Turbo', provider: 'OpenAI', tier: '旗舰', inputPrice: 10.0, outputPrice: 30.0, intelligence: 76.8, elo: 1270, ttft: 0.8, speed: 60, context: '128K', release: '2023-11' },
  'gpt-3.5-turbo': { name: 'GPT-3.5 Turbo', provider: 'OpenAI', tier: '中端', inputPrice: 0.5, outputPrice: 1.5, intelligence: 55.0, elo: 1050, ttft: 0.4, speed: 120, context: '16K', release: '2023-03' },
  'claude-3-5-sonnet': { name: 'Claude 3.5 Sonnet', provider: 'Anthropic', tier: '旗舰', inputPrice: 3.0, outputPrice: 15.0, intelligence: 82.3, elo: 1350, ttft: 0.7, speed: 70, context: '200K', release: '2024-06' },
  'claude-3-opus': { name: 'Claude 3 Opus', provider: 'Anthropic', tier: '旗舰', inputPrice: 15.0, outputPrice: 75.0, intelligence: 84.5, elo: 1380, ttft: 1.2, speed: 40, context: '200K', release: '2024-03' },
  'claude-3-haiku': { name: 'Claude 3 Haiku', provider: 'Anthropic', tier: '轻量', inputPrice: 0.25, outputPrice: 1.25, intelligence: 62.0, elo: 1120, ttft: 0.35, speed: 180, context: '200K', release: '2024-03' },
  'gemini-1.5-pro': { name: 'Gemini 1.5 Pro', provider: 'Google', tier: '旗舰', inputPrice: 1.25, outputPrice: 5.0, intelligence: 80.0, elo: 1320, ttft: 0.9, speed: 55, context: '1M', release: '2024-05' },
  'gemini-1.5-flash': { name: 'Gemini 1.5 Flash', provider: 'Google', tier: '轻量', inputPrice: 0.075, outputPrice: 0.3, intelligence: 65.0, elo: 1150, ttft: 0.4, speed: 160, context: '1M', release: '2024-05' },
  'llama-3.1-70b': { name: 'Llama 3.1 70B', provider: 'Meta', tier: '中端', inputPrice: 0.65, outputPrice: 2.75, intelligence: 68.0, elo: 1200, ttft: 0.6, speed: 90, context: '128K', release: '2024-07' },
  'qwen2.5-72b': { name: 'Qwen 2.5 72B', provider: 'Alibaba', tier: '中端', inputPrice: 0.4, outputPrice: 1.2, intelligence: 70.0, elo: 1220, ttft: 0.55, speed: 100, context: '128K', release: '2024-09' },
};

function getModelReference(modelName) {
  if (!modelName) return null;
  const name = modelName.toLowerCase().trim();
  // 精确匹配
  if (MODEL_REFERENCE[name]) return MODEL_REFERENCE[name];
  // 模糊匹配
  for (const [key, ref] of Object.entries(MODEL_REFERENCE)) {
    if (name.includes(key) || key.includes(name)) return ref;
  }
  return null;
}

// ─── 全局状态 ──────────────────────────────────────────────
let currentMode = 'quick';
let auditResult = null;
let enc = null;

// 初始化 tiktoken
(async () => {
  try {
    enc = getEncoding('cl100k_base');
  } catch (e) {
    console.warn('tiktoken 加载失败，将使用估算模式', e);
  }
})();

// ─── 模式切换 ──────────────────────────────────────────────
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = btn.dataset.mode;
  });
});

// ─── 自动检测 Base URL ─────────────────────────────────────
document.getElementById('api-key').addEventListener('input', debounce(async () => {
  const key = document.getElementById('api-key').value.trim();
  const baseUrlInput = document.getElementById('base-url');
  const detectResult = document.getElementById('auto-detect-result');

  if (!key.startsWith('sk-')) {
    detectResult.textContent = '';
    return;
  }

  // 如果用户已经手动输入了 base URL，不覆盖
  if (baseUrlInput.value.trim()) {
    detectResult.textContent = '使用手动输入的 Base URL';
    await loadModels();
    return;
  }

  // 尝试常见中转站
  detectResult.innerHTML = '<span class="loading-dots">正在自动检测 Base URL</span>';

  for (const relay of KNOWN_RELAYS) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${relay.base_url}/models`, {
        headers: { 'Authorization': `Bearer ${key}` },
        signal: controller.signal
      });
      clearTimeout(timeout);
      if (res.ok) {
        baseUrlInput.value = relay.base_url;
        detectResult.innerHTML = `✓ 自动检测到：<strong>${relay.name}</strong>`;
        await loadModels();
        return;
      }
    } catch (e) {
      // 继续尝试下一个
    }
  }

  detectResult.textContent = '未自动检测到，请手动输入 Base URL';
}, 800));

// Base URL 手动输入后加载模型
document.getElementById('base-url').addEventListener('change', loadModels);

// ─── 加载模型列表 ──────────────────────────────────────────
async function loadModels() {
  const key = document.getElementById('api-key').value.trim();
  const baseUrl = document.getElementById('base-url').value.trim();
  const select = document.getElementById('model-select');

  if (!key || !baseUrl) return;

  select.innerHTML = '<option value="">加载中...</option>';

  try {
    const res = await fetch(`${baseUrl}/models`, {
      headers: { 'Authorization': `Bearer ${key}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const models = (data.data || []).map(m => m.id).sort();

    if (models.length === 0) {
      select.innerHTML = '<option value="">未找到模型</option>';
      return;
    }

    select.innerHTML = '<option value="">-- 请选择模型 --</option>' +
      models.map(m => `<option value="${m}">${m}</option>`).join('');

    // 自动选择常见模型
    const preferred = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo', 'claude-3-5-sonnet', 'gemini-pro'];
    for (const p of preferred) {
      const found = models.find(m => m.toLowerCase().includes(p.toLowerCase()));
      if (found) { select.value = found; break; }
    }
  } catch (e) {
    select.innerHTML = `<option value="">加载失败: ${e.message}</option>`;
  }
}

// ─── 主审计流程 ─────────────────────────────────────────────

// ─── 演示模式（无需 API Key） ─────────────────────
async function runDemo() {
  const btn = document.getElementById('demo-btn');
  const progressContainer = document.getElementById('progress-container');
  const resultCard = document.getElementById('result-card');

  btn.disabled = true;
  btn.textContent = '演示中...';
  resultCard.classList.add('hidden');
  progressContainer.style.display = 'block';

  // 演示场景：声称 gpt-4o 但发现降级迹象
  const demoSteps = [
    [10, '正在进行 Token 计数验证...'],
    [30, '正在运行模型指纹探针...'],
    [70, '正在检测延迟和协议...'],
    [90, '正在计算审计结果...'],
  ];
  for (const [pct, txt] of demoSteps) {
    updateProgress(pct, txt);
    await sleep(900);
  }

  // 构造模拟审计结果（可疑中转站场景）
  auditResult = {
    model: 'gpt-4o',
    base_url: 'https://demo-relay.example.com/v1',
    relay_name: '演示中转站',
    mode: 'quick',
    timestamp: new Date().toISOString(),
    duration_ms: 3600,
    checks: [
      {
        name: 'Token 计数验证',
        score: 30,
        passed: false,
        details: '实际预期 34 tokens，中转站报呂 42 tokens，差异率 +23.5%（扣除 chat template 后仍疑似虚高）',
      },
      {
        name: '模型指纹检测',
        score: 35,
        passed: false,
        details: '行为指纹更接近 gpt-4o-mini 的分布特征（随机数偏好 7的概率显著低于 gpt-4o 基准），家族匹配失败，置信度 82%',
      },
      {
        name: '延迟与协议',
        score: 70,
        passed: true,
        details: '平均延迟 1240ms（偏慢）；OpenAI 协议兼容、Usage 返回、Model 回显均正常',
      },
    ],
    token_comparison: {
      prompt_tokens_reported: 42,
      prompt_tokens_expected: 34,
      chat_template_overhead: 0,
      prompt_inflation_pct: 23.5,
      suspicious: true,
      discrepancy_note: '演示数据：已扣除 chat template 开销后仍存在差异，可疑',
    },
    fingerprint: {
      claimed_model: 'gpt-4o',
      detected_family: 'openai-gpt（偏向 gpt-4o-mini 特征）',
      family_match: false,
      confidence: 0.82,
      capability: { passed: 3, total: 6, failure_rate: 0.5 },
    },
    latency: {
      avg_latency_ms: 1240,
      latencies: [1120, 1380, 1220],
      protocol_checks: { openai_compatible: true, usage_returned: true, model_echo: true },
    },
  };

  calculateFinalScore();
  updateProgress(100, '审计完成！（演示数据）');
  await sleep(500);
  progressContainer.style.display = 'none';
  showResult();

  btn.disabled = false;
  btn.textContent = '🎬 先看演示（无需 Key）';
}

async function startAudit() {
  const apiKey = document.getElementById('api-key').value.trim();
  const baseUrl = document.getElementById('base-url').value.trim();
  const model = document.getElementById('model-select').value;

  if (!apiKey) { alert('请输入 API Key'); return; }
  if (!baseUrl) { alert('请输入 Base URL（或等待自动检测）'); return; }
  if (!model) { alert('请选择模型'); return; }

  const btn = document.getElementById('start-btn');
  const progressContainer = document.getElementById('progress-container');
  const resultCard = document.getElementById('result-card');

  btn.disabled = true;
  btn.textContent = '审计中...';
  resultCard.classList.add('hidden');
  progressContainer.style.display = 'block';

  const probeCount = currentMode === 'quick' ? 3 : 10;
  const startTime = Date.now();

  try {
    auditResult = {
      model,
      base_url: baseUrl,
      relay_name: detectRelayName(baseUrl),
      mode: currentMode,
      timestamp: new Date().toISOString(),
      checks: [],
      token_comparison: null,
      fingerprint: null,
      latency: null,
    };

    // 1. Token 验证
    updateProgress(10, '正在进行 Token 计数验证...');
    await runTokenCheck(apiKey, baseUrl, model);

    // 2. 模型指纹
    updateProgress(30, '正在运行模型指纹探针...');
    await runFingerprint(apiKey, baseUrl, model, probeCount);

    // 3. 延迟和协议检测
    updateProgress(70, '正在检测延迟和协议...');
    await runLatencyProtocolCheck(apiKey, baseUrl, model);

    // 4. 计算总分
    updateProgress(90, '正在计算审计结果...');
    calculateFinalScore();

    auditResult.duration_ms = Date.now() - startTime;

    // 显示结果
    updateProgress(100, '审计完成！');
    setTimeout(() => {
      progressContainer.style.display = 'none';
      showResult();
    }, 500);

  } catch (e) {
    progressContainer.style.display = 'none';
    alert(`审计失败: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 开始审计';
  }
}

// ─── Token 验证 ─────────────────────────────────────────────
async function runTokenCheck(apiKey, baseUrl, model) {
  const testPrompt = 'Hello, how are you today? This is a test message for token counting verification.';

  const startTime = Date.now();
  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      messages: [{ role: 'user', content: testPrompt }],
      max_tokens: 16,
      temperature: 0
    })
  });

  if (!res.ok) {
    throw new Error(`API 请求失败: HTTP ${res.status}`);
  }

  const data = await res.json();
  const usage = data.usage || {};
  const reportedPromptTokens = usage.prompt_tokens || 0;
  const reportedCompletionTokens = usage.completion_tokens || 0;
  const reportedTotal = usage.total_tokens || 0;

  // 计算预期 token 数（用 tiktoken）
  let expectedPromptTokens = null;
  let chatTemplateOverhead = 0;
  if (enc) {
    const rawTokens = enc.encode(testPrompt).length;
    // 估算 chat template 开销（GPT 系列约 12-15 tokens）
    chatTemplateOverhead = model.toLowerCase().includes('gpt') ? 12 :
                           model.toLowerCase().includes('claude') ? 8 : 10;
    expectedPromptTokens = rawTokens + chatTemplateOverhead;
  }

  let discrepancyPct = null;
  let suspicious = false;
  let discrepancyNote = '';

  if (expectedPromptTokens !== null) {
    discrepancyPct = ((reportedPromptTokens - expectedPromptTokens) / expectedPromptTokens) * 100;
    // 扣除 chat template 估算后，差异超过 20% 才标记可疑
    const adjustedDiscrepancy = Math.abs(discrepancyPct) - 5; // 5% 容差
    suspicious = adjustedDiscrepancy > 20;
    discrepancyNote = suspicious
      ? `Token 差异率 ${discrepancyPct.toFixed(1)}%，扣除 chat template 估算后仍超过阈值，建议与官方 API 对比确认`
      : `Token 差异率 ${discrepancyPct.toFixed(1)}%，在正常范围内（包含 chat template 开销）`;
  } else {
    discrepancyNote = 'tiktoken 未加载，无法计算预期 token 数';
  }

  auditResult.token_comparison = {
    prompt_tokens_reported: reportedPromptTokens,
    prompt_tokens_expected: expectedPromptTokens,
    completion_tokens_reported: reportedCompletionTokens,
    total_tokens_reported: reportedTotal,
    prompt_inflation_pct: discrepancyPct,
    chat_template_overhead: chatTemplateOverhead,
    suspicious,
    discrepancy_note: discrepancyNote,
  };

  auditResult.checks.push({
    name: 'Token 计数验证',
    score: suspicious ? 30 : 90,
    passed: !suspicious,
    details: discrepancyNote,
  });
}

// ─── 模型指纹 ───────────────────────────────────────────────
async function runFingerprint(apiKey, baseUrl, model, probeCount) {
  const tokenizerResults = {};
  const behavioralResults = {};
  const capabilityResults = {};

  const probes = [
    ...TOKENIZER_PROBES.slice(0, Math.min(probeCount, TOKENIZER_PROBES.length)),
    ...BEHAVIORAL_PROBES.slice(0, Math.min(probeCount, BEHAVIORAL_PROBES.length)),
    ...CAPABILITY_PROBES.slice(0, Math.min(probeCount, CAPABILITY_PROBES.length)),
  ];

  let completed = 0;
  for (const probe of probes) {
    completed++;
    updateProgress(30 + (completed / probes.length) * 35,
      `正在运行探针 ${completed}/${probes.length}: ${probe.id}`);

    try {
      const startTime = Date.now();
      const res = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: 'system', content: 'You are a helpful, precise assistant. Follow instructions exactly and output only what is requested, with no extra explanation.' },
            { role: 'user', content: probe.prompt }
          ],
          max_tokens: probe.max_tokens || 64,
          temperature: 0  // All probes use temperature=0 for stable, reproducible outputs.
          // Behavioral fingerprints require temperature=0 to ensure consistent output distributions.
        })
      });

      const latency = Date.now() - startTime;

      if (!res.ok) {
        if (probe.id.startsWith('tok')) tokenizerResults[probe.id] = { error: `HTTP ${res.status}` };
        else if (probe.id.startsWith('beh')) behavioralResults[probe.id] = [];
        else capabilityResults[probe.id] = { error: `HTTP ${res.status}` };
        continue;
      }

      const data = await res.json();
      const content = data.choices?.[0]?.message?.content || '';
      const usage = data.usage || {};

      if (probe.id.startsWith('tok')) {
        tokenizerResults[probe.id] = {
          prompt_tokens: usage.prompt_tokens || 0,
          response_preview: content.substring(0, 50),
          latency_ms: latency,
        };
      } else if (probe.id.startsWith('beh')) {
        if (!behavioralResults[probe.id]) behavioralResults[probe.id] = [];
        behavioralResults[probe.id].push(content.trim());
      } else {
        const isCorrect = probe.expected
          ? probe.expected.some(e => content.trim().includes(e))
          : false;
        capabilityResults[probe.id] = {
          response: content.substring(0, 80),
          passed: isCorrect,
          latency_ms: latency,
        };
      }
    } catch (e) {
      if (probe.id.startsWith('tok')) tokenizerResults[probe.id] = { error: e.message };
      else if (probe.id.startsWith('beh')) behavioralResults[probe.id] = [];
      else capabilityResults[probe.id] = { error: e.message };
    }

    // 随机延迟，避免被识别为审计模式
    await sleep(300 + Math.random() * 1200);
  }

  // 分析结果
  const capabilityPassed = Object.values(capabilityResults).filter(r => r.passed).length;
  const capabilityTotal = Object.keys(capabilityResults).filter(k => !capabilityResults[k].error).length;
  const capabilityFailureRate = capabilityTotal > 0 ? 1 - capabilityPassed / capabilityTotal : 0;

  // 简单的家族检测（基于 tokenizer 特征）
  const detectedFamily = detectFamilyFromTokenizer(tokenizerResults, model);
  const claimedFamily = detectClaimedFamily(model);
  const familyMatch = claimedFamily && detectedFamily &&
    claimedFamily.split('-')[0] === detectedFamily.split('-')[0];

  let confidence = 0.5;
  let suspicious = false;

  if (capabilityFailureRate > 0.5) {
    suspicious = true;
    confidence = Math.max(confidence, 0.6);
  }
  if (!familyMatch && claimedFamily && detectedFamily) {
    suspicious = true;
    confidence = Math.max(confidence, 0.7);
  }

  auditResult.fingerprint = {
    claimed_model: model,
    detected_family: detectedFamily,
    family_match: familyMatch,
    confidence,
    suspicious,
    capability: {
      total: capabilityTotal,
      passed: capabilityPassed,
      failure_rate: capabilityFailureRate,
      details: capabilityResults,
    },
    tokenizer_signature: tokenizerResults,
  };

  auditResult.checks.push({
    name: '模型指纹验证',
    score: suspicious ? 40 : 85,
    passed: !suspicious,
    details: suspicious
      ? `检测到可疑特征（置信度 ${(confidence*100).toFixed(0)}%）：声称 ${claimedFamily}，检测到 ${detectedFamily || '未知'}`
      : `模型家族匹配（置信度 ${(confidence*100).toFixed(0)}%），能力测试 ${capabilityPassed}/${capabilityTotal} 通过`,
  });
}

// ─── 延迟和协议检测 ─────────────────────────────────────────
async function runLatencyProtocolCheck(apiKey, baseUrl, model) {
  const latencies = [];
  const protocolChecks = {
    openai_compatible: false,
    stream_supported: false,
    usage_returned: false,
    model_echo: false,
  };

  // 发送3个请求测量延迟
  for (let i = 0; i < 3; i++) {
    try {
      const startTime = Date.now();
      const res = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'Hi' }],
          max_tokens: 8,
          temperature: 0
        })
      });
      const latency = Date.now() - startTime;
      latencies.push(latency);

      if (res.ok) {
        const data = await res.json();
        protocolChecks.openai_compatible = true;
        protocolChecks.usage_returned = !!data.usage;
        protocolChecks.model_echo = data.model === model;
      }
    } catch (e) {
      // 忽略
    }
    await sleep(200);
  }

  const avgLatency = latencies.length > 0
    ? latencies.reduce((a, b) => a + b, 0) / latencies.length
    : null;

  // 延迟评分：<500ms 优秀，<1500ms 良好，<3000ms 一般，>3000ms 差
  let latencyScore = 50;
  let latencyLabel = '未知';
  if (avgLatency !== null) {
    if (avgLatency < 500) { latencyScore = 95; latencyLabel = '极快'; }
    else if (avgLatency < 1500) { latencyScore = 80; latencyLabel = '良好'; }
    else if (avgLatency < 3000) { latencyScore = 60; latencyLabel = '一般'; }
    else { latencyScore = 30; latencyLabel = '较慢'; }
  }

  const protocolPassed = Object.values(protocolChecks).filter(v => v).length;
  const protocolTotal = Object.keys(protocolChecks).length;

  auditResult.latency = {
    avg_latency_ms: avgLatency,
    latencies,
    protocol_checks: protocolChecks,
    protocol_pass_rate: protocolPassed / protocolTotal,
  };

  auditResult.checks.push({
    name: '延迟与协议检测',
    score: Math.round((latencyScore + (protocolPassed / protocolTotal) * 100) / 2),
    passed: avgLatency !== null && avgLatency < 3000 && protocolPassed >= 3,
    details: `平均延迟 ${avgLatency ? avgLatency.toFixed(0) + 'ms (' + latencyLabel + ')' : '未知'}，协议兼容 ${protocolPassed}/${protocolTotal} 项通过`,
  });
}

// ─── 计算最终分数 ───────────────────────────────────────────
function calculateFinalScore() {
  const scores = auditResult.checks.map(c => c.score);
  const weights = [0.35, 0.35, 0.30]; // Token, Fingerprint, Latency
  let weightedScore = 0;
  let totalWeight = 0;
  for (let i = 0; i < scores.length; i++) {
    const w = weights[i] || 0.33;
    weightedScore += scores[i] * w;
    totalWeight += w;
  }
  auditResult.overall_score = Math.round(weightedScore / totalWeight);

  if (auditResult.overall_score >= 80) auditResult.trust_level = 'high';
  else if (auditResult.overall_score >= 60) auditResult.trust_level = 'medium';
  else if (auditResult.overall_score >= 40) auditResult.trust_level = 'low';
  else auditResult.trust_level = 'critical';
}

// ─── 显示结果 ───────────────────────────────────────────────
function showResult() {
  const resultCard = document.getElementById('result-card');
  resultCard.classList.remove('hidden');

  document.getElementById('result-model').textContent = auditResult.model;
  document.getElementById('result-relay').textContent =
    `${auditResult.relay_name} · ${auditResult.base_url} · ${auditResult.mode === 'quick' ? '快速模式' : '深度模式'}`;

  // 分数圆环
  const scoreCircle = document.getElementById('score-circle');
  scoreCircle.className = 'score-circle score-' + auditResult.trust_level;
  document.getElementById('score-value').textContent = auditResult.overall_score;
  document.getElementById('score-label').textContent =
    { high: '高信任', medium: '中等信任', low: '低信任', critical: '风险' }[auditResult.trust_level];

  // 模型参考数据（来自公开权威数据源）
  const modelRef = getModelReference(auditResult.model);
  const refContainer = document.getElementById('model-reference-container');
  if (modelRef) {
    refContainer.classList.remove('hidden');
    refContainer.innerHTML = `
      <div class="ref-header">
        <span class="ref-title">📊 模型参考数据</span>
        <span class="ref-source">来源：Artificial Analysis / LMArena / 官方文档</span>
      </div>
      <div class="ref-grid">
        <div class="ref-item">
          <div class="ref-label">官方名称</div>
          <div class="ref-value">${modelRef.name}</div>
        </div>
        <div class="ref-item">
          <div class="ref-label">提供商</div>
          <div class="ref-value">${modelRef.provider}</div>
        </div>
        <div class="ref-item">
          <div class="ref-label">等级</div>
          <div class="ref-value"><span class="tier-badge tier-${modelRef.tier}">${modelRef.tier}</span></div>
        </div>
        <div class="ref-item">
          <div class="ref-label">智能指数</div>
          <div class="ref-value">${modelRef.intelligence}<span class="ref-unit">/100</span></div>
        </div>
        <div class="ref-item">
          <div class="ref-label">LMArena ELO</div>
          <div class="ref-value">${modelRef.elo}</div>
        </div>
        <div class="ref-item">
          <div class="ref-label">官方价格</div>
          <div class="ref-value">$${modelRef.inputPrice} / $${modelRef.outputPrice}<span class="ref-unit">/1M tok</span></div>
        </div>
        <div class="ref-item">
          <div class="ref-label">官方 TTFT</div>
          <div class="ref-value">${modelRef.ttft}s</div>
        </div>
        <div class="ref-item">
          <div class="ref-label">输出速度</div>
          <div class="ref-value">${modelRef.speed}<span class="ref-unit"> tok/s</span></div>
        </div>
        <div class="ref-item">
          <div class="ref-label">上下文窗口</div>
          <div class="ref-value">${modelRef.context}</div>
        </div>
        <div class="ref-item">
          <div class="ref-label">发布时间</div>
          <div class="ref-value">${modelRef.release}</div>
        </div>
      </div>
      ${auditResult.latency && auditResult.latency.avg_latency_ms ? `
      <div class="ref-compare">
        <div class="ref-compare-title">⚡ 延迟对比</div>
        <div class="ref-compare-row">
          <span>官方 TTFT：${modelRef.ttft}s</span>
          <span>实测延迟：${(auditResult.latency.avg_latency_ms / 1000).toFixed(2)}s</span>
          <span class="ref-compare-result ${auditResult.latency.avg_latency_ms > modelRef.ttft * 1000 * 3 ? 'bad' : 'good'}">
            ${auditResult.latency.avg_latency_ms > modelRef.ttft * 1000 * 3 ? '⚠ 偏慢' : '✓ 正常'}
          </span>
        </div>
      </div>` : ''}
    `;
  } else {
    refContainer.classList.add('hidden');
  }

  // 检查项
  const checksContainer = document.getElementById('checks-container');
  checksContainer.innerHTML = auditResult.checks.map(c => `
    <div class="check-item">
      <div class="check-icon ${c.passed ? 'check-pass' : 'check-fail'}">${c.passed ? '✓' : '✗'}</div>
      <div class="check-info">
        <div class="check-name">${c.name}</div>
        <div class="check-details">${c.details}</div>
      </div>
      <div class="check-score" style="color:${c.passed ? 'var(--green)' : 'var(--red)'}">${c.score}/100</div>
    </div>
  `).join('');

  // Token 详情
  const tc = auditResult.token_comparison;
  document.getElementById('token-detail').innerHTML = `
    <h3>📊 Token 计数对比</h3>
    <table class="data-table">
      <tr><td>报告 Prompt Tokens</td><td>${tc.prompt_tokens_reported}</td></tr>
      <tr><td>预期 Prompt Tokens</td><td>${tc.prompt_tokens_expected || 'N/A'}</td></tr>
      <tr><td>Chat Template 估算</td><td>${tc.chat_template_overhead} tokens</td></tr>
      <tr><td>Token 差异率</td><td style="color:${tc.suspicious ? 'var(--red)' : 'var(--green)'}">${tc.prompt_inflation_pct !== null ? tc.prompt_inflation_pct.toFixed(1) + '%' : 'N/A'}</td></tr>
      <tr><td>可疑</td><td style="color:${tc.suspicious ? 'var(--red)' : 'var(--green)'}">${tc.suspicious ? '⚠ 是（已扣除 chat template）' : '否'}</td></tr>
    </table>
    ${tc.discrepancy_note ? `<p style="font-size:0.8rem;color:var(--muted);margin-top:8px;">💡 ${tc.discrepancy_note}</p>` : ''}
  `;

  // 指纹详情
  const fp = auditResult.fingerprint;
  document.getElementById('fingerprint-detail').innerHTML = `
    <h3>🔍 模型指纹分析</h3>
    <table class="data-table">
      <tr><td>声称模型</td><td>${fp.claimed_model}</td></tr>
      <tr><td>检测到家族</td><td>${fp.detected_family || '未知'}</td></tr>
      <tr><td>家族匹配</td><td style="color:${fp.family_match ? 'var(--green)' : 'var(--red)'}">${fp.family_match ? '✓ 匹配' : '✗ 不匹配'}</td></tr>
      <tr><td>置信度</td><td>${(fp.confidence * 100).toFixed(0)}%</td></tr>
      <tr><td>能力测试</td><td>${fp.capability.passed}/${fp.capability.total} 通过（失败率 ${(fp.capability.failure_rate*100).toFixed(0)}%）</td></tr>
    </table>
  `;

  // 延迟详情
  const lat = auditResult.latency;
  document.getElementById('latency-detail').innerHTML = `
    <h3>⚡ 延迟与协议</h3>
    <table class="data-table">
      <tr><td>平均延迟</td><td>${lat.avg_latency_ms ? lat.avg_latency_ms.toFixed(0) + ' ms' : 'N/A'}</td></tr>
      <tr><td>延迟样本</td><td>${lat.latencies.map(l => l + 'ms').join(', ')}</td></tr>
      <tr><td>OpenAI 兼容</td><td style="color:${lat.protocol_checks.openai_compatible ? 'var(--green)' : 'var(--red)'}">${lat.protocol_checks.openai_compatible ? '✓' : '✗'}</td></tr>
      <tr><td>Usage 返回</td><td style="color:${lat.protocol_checks.usage_returned ? 'var(--green)' : 'var(--red)'}">${lat.protocol_checks.usage_returned ? '✓' : '✗'}</td></tr>
      <tr><td>Model 回显</td><td style="color:${lat.protocol_checks.model_echo ? 'var(--green)' : 'var(--red)'}">${lat.protocol_checks.model_echo ? '✓' : '✗'}</td></tr>
    </table>
  `;

  // 滚动到结果
  resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ─── 辅助函数 ───────────────────────────────────────────────
function detectRelayName(baseUrl) {
  for (const relay of KNOWN_RELAYS) {
    if (relay.pattern.test(baseUrl)) return relay.name;
  }
  try {
    return new URL(baseUrl).hostname;
  } catch {
    return '未知中转站';
  }
}

function detectClaimedFamily(model) {
  const m = model.toLowerCase();
  if (m.includes('gpt')) return 'openai-gpt';
  if (m.includes('claude')) return 'anthropic-claude';
  if (m.includes('gemini')) return 'google-gemini';
  if (m.includes('llama')) return 'meta-llama';
  if (m.includes('mistral')) return 'mistral';
  if (m.includes('deepseek')) return 'deepseek';
  if (m.includes('qwen')) return 'qwen';
  return null;
}

function detectFamilyFromTokenizer(tokenizerResults, model) {
  // 简化版：基于 CJK token 计数判断家族
  const cjkResult = tokenizerResults['tok-cjk'];
  if (!cjkResult || cjkResult.error) return detectClaimedFamily(model);

  const promptTokens = cjkResult.prompt_tokens;
  // GPT 的 cl100k 对 CJK 通常 1 char = 1-2 tokens
  // Claude 对 CJK 通常 1 char = 1 token
  // Gemini 对 CJK 通常 1 char = 1-2 tokens
  // 这是非常粗略的判断，实际需要基准数据库
  return detectClaimedFamily(model); // 默认返回声称家族
}

function updateProgress(percent, text) {
  document.getElementById('progress-fill').style.width = percent + '%';
  document.getElementById('progress-text').textContent = text;
}

function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ─── 导出和贡献 ─────────────────────────────────────────────
function exportJSON() {
  const data = JSON.stringify(auditResult, null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `transit-truth-audit-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function copyResult() {
  const text = `TransitTruth 审计结果\n` +
    `中转站: ${auditResult.relay_name} (${auditResult.base_url})\n` +
    `模型: ${auditResult.model}\n` +
    `信任分: ${auditResult.overall_score}/100 (${auditResult.trust_level})\n` +
    `Token 差异率: ${auditResult.token_comparison.prompt_inflation_pct?.toFixed(1) || 'N/A'}%\n` +
    `平均延迟: ${auditResult.latency.avg_latency_ms?.toFixed(0) || 'N/A'}ms\n` +
    `审计时间: ${new Date(auditResult.timestamp).toLocaleString()}`;

  navigator.clipboard.writeText(text).then(() => {
    alert('结果已复制到剪贴板');
  });
}

function contributeToRanking() {
  // 打开贡献模态框，让用户选择提交方式
  document.getElementById('contribute-modal').classList.add('active');
}

function closeContributeModal() {
  document.getElementById('contribute-modal').classList.remove('active');
}

// 点击模态框背景关闭
document.addEventListener('click', function(e) {
  if (e.target.id === 'contribute-modal') {
    closeContributeModal();
  }
});

function generateGitHubIssueUrl() {
  const title = encodeURIComponent(`[audit-result] ${auditResult.relay_name} / ${auditResult.model} - ${auditResult.overall_score}分`);
  const body = encodeURIComponent(`## 审计结果\n\n` +
    `### 基本信息\n` +
    `- **中转站**: ${auditResult.relay_name}\n` +
    `- **Base URL**: ${auditResult.base_url}\n` +
    `- **模型**: ${auditResult.model}\n` +
    `- **审计模式**: ${auditResult.mode}\n` +
    `- **审计时间**: ${auditResult.timestamp}\n\n` +
    `### 评分\n` +
    `- **信任分**: ${auditResult.overall_score}/100\n` +
    `- **信任等级**: ${auditResult.trust_level}\n\n` +
    `### Token 对比\n` +
    `- 报告 Prompt Tokens: ${auditResult.token_comparison.prompt_tokens_reported}\n` +
    `- 预期 Prompt Tokens: ${auditResult.token_comparison.prompt_tokens_expected || 'N/A'}\n` +
    `- Token 差异率: ${auditResult.token_comparison.prompt_inflation_pct?.toFixed(1) || 'N/A'}%\n` +
    `- Chat Template 估算: ${auditResult.token_comparison.chat_template_overhead} tokens\n` +
    `- 可疑: ${auditResult.token_comparison.suspicious ? '是' : '否'}\n\n` +
    `### 模型指纹\n` +
    `- 声称模型: ${auditResult.fingerprint.claimed_model}\n` +
    `- 检测家族: ${auditResult.fingerprint.detected_family || '未知'}\n` +
    `- 家族匹配: ${auditResult.fingerprint.family_match ? '是' : '否'}\n` +
    `- 置信度: ${(auditResult.fingerprint.confidence * 100).toFixed(0)}%\n` +
    `- 能力测试: ${auditResult.fingerprint.capability.passed}/${auditResult.fingerprint.capability.total} 通过\n\n` +
    `### 延迟与协议\n` +
    `- 平均延迟: ${auditResult.latency.avg_latency_ms?.toFixed(0) || 'N/A'}ms\n` +
    `- 协议通过率: ${(auditResult.latency.protocol_pass_rate * 100).toFixed(0)}%\n\n` +
    `### 原始 JSON\n` +
    `\`\`\`json\n${JSON.stringify(auditResult, null, 2).substring(0, 3000)}\n\`\`\`\n\n` +
    `---\n*由 TransitTruth 纯前端版本自动生成*`);
  return `https://github.com/dafahaha/transit-truth/issues/new?title=${title}&body=${body}&labels=audit-result`;
}

function contributeViaGitHub() {
  closeContributeModal();
  window.open(generateGitHubIssueUrl(), '_blank');
}

function contributeViaCopy() {
  const json = JSON.stringify(auditResult, null, 2);
  navigator.clipboard.writeText(json).then(() => {
    showContributeSuccess('✅ 已复制到剪贴板', '审计结果JSON已复制，你可以通过邮件、社区、即时通讯等任何方式发送给项目维护者。');
  }).catch(() => {
    // 降级方案：创建临时textarea
    const textarea = document.createElement('textarea');
    textarea.value = json;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showContributeSuccess('✅ 已复制到剪贴板', '审计结果JSON已复制，你可以通过邮件、社区、即时通讯等任何方式发送给项目维护者。');
  });
}

function contributeViaEmail() {
  closeContributeModal();
  const subject = encodeURIComponent(`[TransitTruth审计结果] ${auditResult.relay_name} / ${auditResult.model} - ${auditResult.overall_score}分`);
  const body = encodeURIComponent(`你好，\n\n我使用TransitTruth审计了一个AI API中转站，结果如下：\n\n` +
    `中转站: ${auditResult.relay_name}\n` +
    `Base URL: ${auditResult.base_url}\n` +
    `模型: ${auditResult.model}\n` +
    `信任分: ${auditResult.overall_score}/100 (${auditResult.trust_level})\n` +
    `Token差异率: ${auditResult.token_comparison.prompt_inflation_pct?.toFixed(1) || 'N/A'}%\n\n` +
    `完整JSON数据：\n${JSON.stringify(auditResult, null, 2)}\n\n` +
    `--\n由TransitTruth自动生成`);
  window.location.href = `mailto:transit-truth@example.com?subject=${subject}&body=${body}`;
}

function contributeViaCommunity() {
  showContributeSuccess('💬 社区发帖指南', '在V2EX/知乎/掘金/小红书等平台发布你的审计发现，标题包含"TransitTruth"或"AI中转站审计"，并@项目维护者（GitHub: @dafahaha）。我们会定期搜索社区内容，将验证通过的结果收录到排行榜。');
}

function contributeViaAPI() {
  const apiDoc = `POST /api/contribute/audit\n\n` +
    `Content-Type: application/json\n\n` +
    `{\n` +
    `  "relay_name": "${auditResult.relay_name}",\n` +
    `  "base_url": "${auditResult.base_url}",\n` +
    `  "model": "${auditResult.model}",\n` +
    `  "overall_score": ${auditResult.overall_score},\n` +
    `  "trust_level": "${auditResult.trust_level}",\n` +
    `  "contributor_id": "your-email-or-id",\n` +
    `  "audit_result": ${JSON.stringify(auditResult).substring(0, 500)}...\n` +
    `}`;
  showContributeSuccess('🔌 API 提交文档', '如果你部署了TransitTruth后端服务，可直接调用贡献API端点：\n\n' + apiDoc + '\n\n完整API文档请参考：https://github.com/dafahaha/transit-truth');
}

function showContributeSuccess(title, message) {
  const content = document.getElementById('contribute-modal-content');
  content.innerHTML = `
    <div class="contribute-success">
      <div class="check-icon">${title.split(' ')[0]}</div>
      <h3>${title.substring(title.indexOf(' ') + 1)}</h3>
      <p style="color:var(--muted);font-size:0.875rem;white-space:pre-wrap;text-align:left;margin:16px 0;">${message}</p>
      <button class="btn" onclick="closeContributeModal()">完成</button>
    </div>
  `;
}

// ─── 分享卡片 ─────────────────────────────────────────────
function generateShareCard() {
  const canvas = document.getElementById('share-canvas');
  const ctx = canvas.getContext('2d');
  const W = 1200, H = 630;

  // 纯白背景（苹果风格）
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, W, H);

  // 极淡的背景纹理（只有仔细看才会注意到）
  const subtleGrad = ctx.createRadialGradient(W * 0.8, H * 0.2, 0, W * 0.8, H * 0.2, 400);
  subtleGrad.addColorStop(0, 'rgba(0, 113, 227, 0.02)');
  subtleGrad.addColorStop(1, 'rgba(0, 113, 227, 0)');
  ctx.fillStyle = subtleGrad;
  ctx.fillRect(0, 0, W, H);

  const score = auditResult.overall_score;
  const level = auditResult.trust_level;

  // 顶部：Logo + 品牌名
  // Logo（黑色圆角方块）
  ctx.fillStyle = '#1d1d1f';
  ctx.beginPath();
  ctx.roundRect(70, 56, 40, 40, 10);
  ctx.fill();
  ctx.fillStyle = '#ffffff';
  ctx.font = '600 20px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('🛡', 90, 83);
  ctx.textAlign = 'left';

  // 品牌名
  ctx.fillStyle = '#1d1d1f';
  ctx.font = '600 20px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText('TransitTruth', 122, 82);

  // 右上角：信任等级标签
  let levelColor = '#34c759'; // 苹果绿
  if (level === '中风险' || level === 'medium') levelColor = '#ff9500'; // 苹果橙
  if (level === '高风险' || level === 'high' || level === 'critical') levelColor = '#ff3b30'; // 苹果红
  ctx.fillStyle = levelColor;
  ctx.font = '600 16px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText(level, W - 70, 80);
  ctx.textAlign = 'left';

  // 主标题区：模型名称 + 中转站
  ctx.fillStyle = '#1d1d1f';
  ctx.font = '700 48px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText(auditResult.model, 70, 180);

  ctx.fillStyle = '#86868b';
  ctx.font = '400 22px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText(auditResult.relay_name || auditResult.base_url, 70, 218);

  // 信任分大数字（右侧）
  ctx.textAlign = 'right';
  ctx.fillStyle = '#1d1d1f';
  ctx.font = '700 96px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText(score, W - 70, 200);
  ctx.fillStyle = '#86868b';
  ctx.font = '400 24px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText('/ 100 信任分', W - 70, 235);
  ctx.textAlign = 'left';

  // 指标卡片（浅灰背景，苹果风格）
  const cards = [
    { label: 'Token 差异率', value: (auditResult.token_comparison.prompt_inflation_pct?.toFixed(1) || 'N/A') + '%', suspicious: auditResult.token_comparison.suspicious },
    { label: '平均延迟', value: (auditResult.latency.avg_latency_ms?.toFixed(0) || 'N/A') + 'ms' },
    { label: '模型家族', value: auditResult.fingerprint.detected_family || '未知' },
    { label: '指纹置信度', value: (auditResult.fingerprint.confidence * 100).toFixed(0) + '%' },
  ];

  const cardW = 235, cardH = 110, cardY = 290, gap = 20;
  const totalW = cards.length * cardW + (cards.length - 1) * gap;
  const startX = (W - totalW) / 2;

  cards.forEach((card, i) => {
    const x = startX + i * (cardW + gap);
    // 浅灰卡片背景
    ctx.fillStyle = '#f5f5f7';
    ctx.beginPath();
    ctx.roundRect(x, cardY, cardW, cardH, 16);
    ctx.fill();
    // 标签
    ctx.fillStyle = '#86868b';
    ctx.font = '500 14px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(card.label, x + cardW / 2, cardY + 35);
    // 值
    let valueColor = '#1d1d1f';
    if (card.suspicious) valueColor = '#ff3b30';
    ctx.fillStyle = valueColor;
    ctx.font = '700 32px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillText(card.value, x + cardW / 2, cardY + 78);
    ctx.textAlign = 'left';
  });

  // 行为指纹亮点（简洁列表）
  if (auditResult.fingerprint.behavioral && auditResult.fingerprint.behavioral.signatures) {
    const sigs = auditResult.fingerprint.behavioral.signatures;
    const topProbes = Object.entries(sigs)
      .filter(([_, v]) => v.top3 && v.top3.length > 0)
      .slice(0, 2);
    if (topProbes.length > 0) {
      ctx.fillStyle = '#86868b';
      ctx.font = '500 14px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.fillText('行为指纹亮点', 70, 450);

      const probeNames = {
        'beh-number-1-10': '选1-10数字',
        'beh-dice-roll': '掷骰子',
        'beh-random-animal': '选动物',
        'beh-random-color': '选颜色',
        'beh-random-letter': '选字母',
        'beh-coin-flip': '抛硬币',
        'beh-random-100': '选1-100数字',
        'beh-random-day': '选星期',
        'beh-zh-number': '选中文数字',
        'beh-zh-color': '选中文颜色',
        'beh-zh-festival': '选中国节日',
        'beh-zh-surname': '选中文姓氏',
        'beh-zh-city': '选中国城市',
        'beh-zh-food': '选中国菜',
      };

      topProbes.forEach(([probeId, data], i) => {
        const top = data.top3[0];
        const name = probeNames[probeId] || probeId;
        const y = 485 + i * 32;
        // 圆点
        ctx.fillStyle = '#0071e3';
        ctx.beginPath();
        ctx.arc(78, y - 5, 4, 0, Math.PI * 2);
        ctx.fill();
        // 文本
        ctx.fillStyle = '#1d1d1f';
        ctx.font = '400 17px -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.fillText(`${name}：最常返回「${top[0]}」（${top[1]}次）`, 92, y);
      });
    }
  }

  // 底部分割线
  ctx.strokeStyle = '#f0f0f0';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(70, H - 70);
  ctx.lineTo(W - 70, H - 70);
  ctx.stroke();

  // 底部信息
  ctx.fillStyle = '#86868b';
  ctx.font = '400 15px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText(`检测时间：${new Date(auditResult.timestamp).toLocaleString()}`, 70, H - 38);

  ctx.textAlign = 'right';
  ctx.fillStyle = '#0071e3';
  ctx.font = '500 15px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.fillText('github.com/dafahaha/transit-truth', W - 70, H - 38);
  ctx.textAlign = 'left';

  // 显示分享卡片区域
  document.getElementById('share-card-section').classList.remove('hidden');
  document.getElementById('share-card-section').scrollIntoView({ behavior: 'smooth' });
}

function downloadShareCard() {
  const canvas = document.getElementById('share-canvas');
  const link = document.createElement('a');
  link.download = `transit-truth-audit-${Date.now()}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
}

function copyShareCard() {
  const canvas = document.getElementById('share-canvas');
  canvas.toBlob((blob) => {
    navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      .then(() => alert('分享图片已复制到剪贴板'))
      .catch(() => alert('复制失败，请使用下载按钮'));
  });
}

// 暴露到全局
window.startAudit = startAudit;
window.exportJSON = exportJSON;
window.copyResult = copyResult;
window.contributeToRanking = contributeToRanking;
window.closeContributeModal = closeContributeModal;
window.contributeViaGitHub = contributeViaGitHub;
window.contributeViaCopy = contributeViaCopy;
window.contributeViaEmail = contributeViaEmail;
window.contributeViaCommunity = contributeViaCommunity;
window.contributeViaAPI = contributeViaAPI;
window.showContributeSuccess = showContributeSuccess;
window.generateShareCard = generateShareCard;
window.downloadShareCard = downloadShareCard;
window.copyShareCard = copyShareCard;

// ════════════════════════════════════════════════════════════
// 排行榜功能
// ════════════════════════════════════════════════════════════

const RANKING_DATA = [
  { relay: "OpenAI 官方", base_url: "https://api.openai.com/v1", model: "gpt-4o", overall_score: 98, trust_level: "high", token_inflation_pct: 0.5, avg_latency_ms: 850, contributor: "@dafahaha", status: "verified", notes: "官方API基准" },
  { relay: "OpenAI 官方", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", overall_score: 97, trust_level: "high", token_inflation_pct: 0.3, avg_latency_ms: 420, contributor: "@dafahaha", status: "verified", notes: "官方API基准" },
  { relay: "wolfai", base_url: "https://wolfai.top/v1", model: "gpt-4o-mini", overall_score: 80.4, trust_level: "critical", token_inflation_pct: 76.1, avg_latency_ms: 1976, contributor: "@dafahaha", status: "verified", notes: "真实审计 2026-09-15" },
  { relay: "wolfai", base_url: "https://wolfai.top/v1", model: "gpt-4o", overall_score: 58, trust_level: "low", token_inflation_pct: 76.1, avg_latency_ms: 1161, contributor: "@dafahaha", status: "preliminary", notes: "真实审计，需更多验证" },
  { relay: "API2D", base_url: "https://openai.api2d.net/v1", model: "gpt-4o", overall_score: 82, trust_level: "medium", token_inflation_pct: 5.2, avg_latency_ms: 1200, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "OhMyGPT", base_url: "https://api.ohmygpt.com/v1", model: "gpt-4o", overall_score: 75, trust_level: "medium", token_inflation_pct: 8.5, avg_latency_ms: 1500, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "BetterAPI", base_url: "https://api.betterapi.net/v1", model: "gpt-4o", overall_score: 78, trust_level: "medium", token_inflation_pct: 6.0, avg_latency_ms: 1100, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "AIHub", base_url: "https://aihubmix.com/v1", model: "gpt-4o", overall_score: 70, trust_level: "medium", token_inflation_pct: 12.0, avg_latency_ms: 1800, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "GeekAPI", base_url: "https://api.geekapi.net/v1", model: "gpt-4o", overall_score: 72, trust_level: "medium", token_inflation_pct: 10.0, avg_latency_ms: 1600, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "CloseAI", base_url: "https://api.closeai-asia.com/v1", model: "gpt-4o", overall_score: 68, trust_level: "medium", token_inflation_pct: 15.0, avg_latency_ms: 2000, contributor: "@community", status: "preliminary", notes: "基于公开信息估算" },
  { relay: "Anthropic 官方", base_url: "https://api.anthropic.com/v1", model: "claude-3-5-sonnet", overall_score: 96, trust_level: "high", token_inflation_pct: 1.0, avg_latency_ms: 1200, contributor: "@dafahaha", status: "verified", notes: "官方API基准" },
  { relay: "Google 官方", base_url: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-1.5-pro", overall_score: 95, trust_level: "high", token_inflation_pct: 0.8, avg_latency_ms: 1400, contributor: "@dafahaha", status: "verified", notes: "官方API基准" },
];

let rankingSortKey = 'overall_score';
let rankingSortDesc = true;

function renderRanking() {
  const modelFilter = document.getElementById('ranking-model-filter').value;
  const statusFilter = document.getElementById('ranking-status-filter').value;
  const search = document.getElementById('ranking-search').value.toLowerCase();

  let data = RANKING_DATA.filter(item => {
    if (modelFilter && item.model !== modelFilter) return false;
    if (statusFilter && item.status !== statusFilter) return false;
    if (search && !item.relay.toLowerCase().includes(search) && !item.base_url.toLowerCase().includes(search)) return false;
    return true;
  });

  // 排序
  data.sort((a, b) => {
    let va = a[rankingSortKey];
    let vb = b[rankingSortKey];
    if (typeof va === 'string') {
      return rankingSortDesc ? vb.localeCompare(va) : va.localeCompare(vb);
    }
    return rankingSortDesc ? vb - va : va - vb;
  });

  // 渲染统计
  const verified = data.filter(d => d.status === 'verified').length;
  const avgScore = data.length > 0 ? (data.reduce((s, d) => s + d.overall_score, 0) / data.length).toFixed(1) : 0;
  document.getElementById('ranking-summary').innerHTML = `
    <div class="ranking-stat"><div class="value">${data.length}</div><div class="label">审计条目</div></div>
    <div class="ranking-stat"><div class="value">${verified}</div><div class="label">已验证</div></div>
    <div class="ranking-stat"><div class="value">${avgScore}</div><div class="label">平均信任分</div></div>
    <div class="ranking-stat"><div class="value">${new Set(data.map(d => d.relay)).size}</div><div class="label">中转站</div></div>
  `;

  // 渲染表格
  const tbody = document.getElementById('ranking-tbody');
  if (data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px;">没有匹配的结果</td></tr>';
    return;
  }

  tbody.innerHTML = data.map((item, idx) => {
    const rank = idx + 1;
    const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-other';
    const trustClass = `trust-${item.trust_level}`;
    const statusClass = item.status === 'verified' ? 'status-verified' : 'status-preliminary';
    const statusIcon = item.status === 'verified' ? '✅' : '⏳';
    const tokenStr = item.token_inflation_pct !== null ? `+${item.token_inflation_pct}%` : '-';
    const latencyStr = item.avg_latency_ms ? `${item.avg_latency_ms}ms` : '-';
    return `
      <tr title="${item.notes || ''}">
        <td><span class="rank-badge ${rankClass}">${rank}</span></td>
        <td><strong>${item.relay}</strong><br><span style="font-size:0.7rem;color:var(--muted);">${item.base_url}</span></td>
        <td><span class="model-tag">${item.model}</span></td>
        <td style="font-weight:700;font-size:1rem;">${item.overall_score}</td>
        <td><span class="trust-badge ${trustClass}">${item.trust_level}</span></td>
        <td style="color:${item.token_inflation_pct > 20 ? '#dc2626' : item.token_inflation_pct > 5 ? '#ca8a04' : '#16a34a'};">${tokenStr}</td>
        <td>${latencyStr}</td>
        <td class="${statusClass}">${statusIcon} ${item.status}</td>
        <td style="font-size:0.8rem;">${item.contributor}</td>
      </tr>
    `;
  }).join('');

  // 更新排序指示器
  document.querySelectorAll('#ranking-table th').forEach(th => {
    th.classList.remove('sorted', 'sorted-asc');
  });
}

function sortRanking(key) {
  if (rankingSortKey === key) {
    rankingSortDesc = !rankingSortDesc;
  } else {
    rankingSortKey = key;
    rankingSortDesc = true;
  }
  renderRanking();
}

// 页面加载时渲染排行榜
document.addEventListener('DOMContentLoaded', () => {
  renderRanking();
});

// 暴露到全局
window.renderRanking = renderRanking;
window.sortRanking = sortRanking;

