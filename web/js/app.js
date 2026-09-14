/**
 * TransitTruth - Pure Frontend Demo
 * All API calls are made directly from the browser, no backend required.
 */

// ─── Known Relay Base URLs for auto-detection ───────────────────────
const KNOWN_RELAYS = [
    { name: 'OpenAI Official', baseUrl: 'https://api.openai.com/v1', pattern: 'api.openai.com' },
    { name: 'Azure OpenAI', baseUrl: 'https://*.openai.azure.com', pattern: 'openai.azure.com' },
    { name: 'WolfAI', baseUrl: 'https://wolfai.top/v1', pattern: 'wolfai.top' },
    { name: 'API2D', baseUrl: 'https://openai.api2d.net/v1', pattern: 'api2d.net' },
    { name: 'OhMyGPT', baseUrl: 'https://api.ohmygpt.com/v1', pattern: 'ohmygpt.com' },
    { name: 'AIHubMix', baseUrl: 'https://aihubmix.com/v1', pattern: 'aihubmix.com' },
    { name: 'CloseAI', baseUrl: 'https://api.closeai-asia.com/v1', pattern: 'closeai' },
    { name: 'NewAPI', baseUrl: 'https://*.newapi.pro/v1', pattern: 'newapi' },
    { name: 'OneAPI', baseUrl: 'https://*/v1', pattern: 'one-api' },
    { name: '中转站 (通用)', baseUrl: '', pattern: '' },
];

// ─── Probe Definitions ───────────────────────────────────────────────
const TOKENIZER_PROBES = [
    { id: 'tok-digits', prompt: 'Repeat this string exactly: 123456789012345678901234567890', expectedRange: [15, 35] },
    { id: 'tok-cjk', prompt: 'Repeat this string exactly: 人工智能强化学习具身智能机器人视觉语言模型', expectedRange: [10, 40] },
    { id: 'tok-emoji', prompt: 'Repeat this string exactly: 🤖🧠🚀💻🎯🔥✨🌟💡🎨', expectedRange: [10, 50] },
    { id: 'tok-code', prompt: 'Repeat this string exactly: def foo(x): return x*2+1  # test', expectedRange: [10, 30] },
];

const BEHAVIORAL_PROBES = [
    { id: 'beh-random-100', prompt: 'Pick a random number between 1 and 100. Reply with ONLY the number.', maxTokens: 8 },
    { id: 'beh-random-color', prompt: 'Name a random color. Reply with ONLY the color name.', maxTokens: 8 },
    { id: 'beh-coin-flip', prompt: 'Flip a coin. Reply with ONLY heads or tails.', maxTokens: 4 },
    { id: 'beh-dice-roll', prompt: 'Roll a six-sided die. Reply with ONLY the number 1-6.', maxTokens: 4 },
];

const CAPABILITY_PROBES = [
    { id: 'cap-simple-math', prompt: 'What is 17 * 23? Reply with ONLY the number.', expected: ['391'], maxTokens: 8 },
    { id: 'cap-logic', prompt: 'If all cats are animals and some animals are black, can we conclude some cats are black? Answer yes or no only.', expected: ['no', 'No', 'NO'], maxTokens: 4 },
    { id: 'cap-reasoning', prompt: 'A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Reply with ONLY the number of cents.', expected: ['5', '5 cents'], maxTokens: 8 },
    { id: 'cap-following', prompt: 'Count from 1 to 5, but skip 3. Reply with ONLY the numbers separated by commas.', expected: ['1,2,4,5', '1, 2, 4, 5'], maxTokens: 16 },
];

// ─── State ────────────────────────────────────────────────────────────
let tiktokenEncoder = null;
let currentAudit = null;

// ─── DOM Elements ─────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ─── Initialization ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadHistory();
    initTiktoken();
});

async function initTiktoken() {
    try {
        if (typeof Tiktoken !== 'undefined') {
            tiktokenEncoder = Tiktoken.getEncoding('cl100k_base');
            console.log('tiktoken initialized (cl100k_base)');
        }
    } catch (e) {
        console.warn('tiktoken init failed, using fallback token counting:', e.message);
    }
}

function initEventListeners() {
    // API Key input
    $('apiKey').addEventListener('input', validateForm);
    $('baseUrl').addEventListener('input', handleBaseUrlInput);

    // Model select
    $('model').addEventListener('change', (e) => {
        $('customModel').style.display = e.target.value === 'custom' ? 'block' : 'none';
    });

    // Mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // Start button
    $('startBtn').addEventListener('click', startAudit);

    // Restart button
    $('restartBtn').addEventListener('click', resetToInput);

    // Export button
    $('exportBtn').addEventListener('click', exportReport);

    // Contribute button
    $('contributeBtn').addEventListener('click', contributeToRanking);
}

function validateForm() {
    const apiKey = $('apiKey').value.trim();
    $('startBtn').disabled = !apiKey.startsWith('sk-');
}

function handleBaseUrlInput() {
    const url = $('baseUrl').value.trim();
    const detected = KNOWN_RELAYS.find(r => url.includes(r.pattern) && r.pattern);
    const el = $('detectedRelay');
    if (detected) {
        el.textContent = `✓ 已识别: ${detected.name}`;
        el.style.display = 'block';
    } else {
        el.style.display = 'none';
    }
}

// ─── Audit Flow ────────────────────────────────────────────────────────
async function startAudit() {
    const apiKey = $('apiKey').value.trim();
    let baseUrl = $('baseUrl').value.trim();
    const modelSelect = $('model').value;
    const model = modelSelect === 'custom' ? $('customModel').value.trim() : modelSelect;
    const mode = document.querySelector('.mode-btn.active').dataset.mode;

    if (!baseUrl) {
        baseUrl = 'https://api.openai.com/v1';
        $('baseUrl').value = baseUrl;
    }

    if (!model) {
        alert('请选择或输入模型名称');
        return;
    }

    // Switch to running step
    showStep('step-running');
    updateProgress(0, '初始化...');

    currentAudit = {
        apiKey,
        baseUrl,
        model,
        mode,
        startTime: Date.now(),
        results: {},
    };

    try {
        // Run all checks
        await runLatencyCheck();
        await runTokenCheck();
        await runFingerprintCheck();
        await runCapabilityCheck();

        // Calculate final score
        calculateFinalScore();

        // Save to history
        saveToHistory();

        // Show results
        showStep('step-result');
        renderResults();

    } catch (error) {
        console.error('Audit failed:', error);
        updateProgress(100, '检测失败: ' + error.message);
        setTimeout(() => {
            alert('检测失败: ' + error.message + '\n\n请检查 API Key 和 Base URL 是否正确。');
            resetToInput();
        }, 1000);
    }
}

async function runLatencyCheck() {
    updateStatus('latencyStatus', 'running', '检测中...');
    updateProgress(10, '延迟检测中...');

    const latencies = [];
    const numRequests = 3;

    for (let i = 0; i < numRequests; i++) {
        const startTime = performance.now();
        try {
            await makeApiCall('Hello', 5);
            const latency = performance.now() - startTime;
            latencies.push(latency);
        } catch (e) {
            throw new Error('API 调用失败: ' + e.message);
        }
    }

    const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;
    currentAudit.results.latency = {
        latencies,
        avgLatency,
        minLatency: Math.min(...latencies),
        maxLatency: Math.max(...latencies),
    };

    updateStatus('latencyStatus', 'done', `完成 (${avgLatency.toFixed(0)}ms)`);
}

async function runTokenCheck() {
    updateStatus('tokenStatus', 'running', '检测中...');
    updateProgress(30, 'Token 计数验证中...');

    const testPrompt = 'Translate "Hello, how are you?" to French.';
    const result = await makeApiCall(testPrompt, 50);

    const usage = result.usage || {};
    const reportedPromptTokens = usage.prompt_tokens || 0;
    const reportedCompletionTokens = usage.completion_tokens || 0;
    const reportedTotalTokens = usage.total_tokens || 0;

    // Calculate expected tokens using tiktoken
    let expectedPromptTokens = null;
    let chatTemplateOverhead = 0;
    if (tiktokenEncoder) {
        try {
            // Raw prompt tokens
            const rawTokens = tiktokenEncoder.encode(testPrompt).length;
            // Chat template overhead estimate (system + user markers)
            chatTemplateOverhead = 12; // approximate for gpt-4 style
            expectedPromptTokens = rawTokens + chatTemplateOverhead;
        } catch (e) {
            console.warn('Token counting failed:', e);
        }
    }

    let discrepancyPct = null;
    let suspicious = false;
    let discrepancyNote = '';

    if (expectedPromptTokens !== null && expectedPromptTokens > 0) {
        discrepancyPct = ((reportedPromptTokens - expectedPromptTokens) / expectedPromptTokens) * 100;
        // Suspicious if > 20% after accounting for chat template
        suspicious = Math.abs(discrepancyPct) > 20;
        discrepancyNote = suspicious
            ? '差异较大，可能存在Token计数差异，建议与官方API对比确认'
            : '差异在正常范围内（包含chat template开销）';
    }

    currentAudit.results.token = {
        reportedPromptTokens,
        reportedCompletionTokens,
        reportedTotalTokens,
        expectedPromptTokens,
        chatTemplateOverhead,
        discrepancyPct,
        suspicious,
        discrepancyNote,
    };

    updateStatus('tokenStatus', 'done', suspicious ? '⚠ 发现差异' : '完成');
}

async function runFingerprintCheck() {
    updateStatus('fingerprintStatus', 'running', '检测中...');
    updateProgress(50, '模型指纹检测中...');

    const tokenizerResults = [];
    const behavioralResults = [];

    // Run tokenizer probes
    for (const probe of TOKENIZER_PROBES) {
        try {
            const result = await makeApiCall(probe.prompt, 64);
            const usage = result.usage || {};
            tokenizerResults.push({
                id: probe.id,
                promptTokens: usage.prompt_tokens || 0,
                expectedRange: probe.expectedRange,
                inRange: usage.prompt_tokens >= probe.expectedRange[0] && usage.prompt_tokens <= probe.expectedRange[1],
            });
        } catch (e) {
            console.warn(`Probe ${probe.id} failed:`, e);
        }
        await sleep(300 + Math.random() * 500); // Random delay
    }

    // Run behavioral probes (2 samples each)
    for (const probe of BEHAVIORAL_PROBES) {
        const responses = [];
        for (let i = 0; i < 2; i++) {
            try {
                const result = await makeApiCall(probe.prompt, probe.maxTokens, 1.0);
                const content = result.choices?.[0]?.message?.content?.trim() || '';
                responses.push(content);
            } catch (e) {
                console.warn(`Behavioral probe ${probe.id} failed:`, e);
            }
            await sleep(200 + Math.random() * 300);
        }
        behavioralResults.push({ id: probe.id, responses });
    }

    // Analyze fingerprint
    const tokenizerAnomalies = tokenizerResults.filter(r => !r.inRange).length;
    const fingerprintSuspicious = tokenizerAnomalies > tokenizerResults.length * 0.5;
    const confidence = tokenizerResults.length > 0
        ? 0.5 + (tokenizerAnomalies / tokenizerResults.length) * 0.3
        : 0.5;

    currentAudit.results.fingerprint = {
        tokenizerResults,
        behavioralResults,
        tokenizerAnomalies,
        totalTokenizerProbes: tokenizerResults.length,
        suspicious: fingerprintSuspicious,
        confidence: Math.min(confidence, 0.9),
        detectedFamily: fingerprintSuspicious ? '可能与声称模型不同' : '与声称模型一致',
    };

    updateStatus('fingerprintStatus', 'done', fingerprintSuspicious ? '⚠ 可疑' : '完成');
}

async function runCapabilityCheck() {
    updateStatus('capabilityStatus', 'running', '检测中...');
    updateProgress(75, '能力测试中...');

    const results = [];
    let passed = 0;

    for (const probe of CAPABILITY_PROBES) {
        try {
            const result = await makeApiCall(probe.prompt, probe.maxTokens, 0);
            const content = result.choices?.[0]?.message?.content?.trim() || '';
            const isCorrect = probe.expected.some(exp => content.includes(exp));
            if (isCorrect) passed++;
            results.push({
                id: probe.id,
                response: content.substring(0, 50),
                passed: isCorrect,
            });
        } catch (e) {
            console.warn(`Capability probe ${probe.id} failed:`, e);
            results.push({ id: probe.id, response: 'ERROR', passed: false });
        }
        await sleep(200 + Math.random() * 300);
    }

    const passRate = results.length > 0 ? passed / results.length : 0;
    const suspicious = passRate < 0.5;

    currentAudit.results.capability = {
        results,
        passed,
        total: results.length,
        passRate,
        suspicious,
        tierEstimate: passRate >= 0.75 ? 'high' : passRate >= 0.5 ? 'medium' : 'low',
    };

    updateStatus('capabilityStatus', 'done', `${passed}/${results.length} 通过`);
}

function calculateFinalScore() {
    updateProgress(90, '计算最终评分...');

    const { latency, token, fingerprint, capability } = currentAudit.results;

    // Latency score (0-100): lower is better, 500ms = 100, 5000ms = 0
    const latencyScore = Math.max(0, Math.min(100, 100 - (latency.avgLatency - 500) / 45));

    // Token score (0-100)
    let tokenScore = 100;
    if (token.suspicious) tokenScore = 40;
    else if (token.discrepancyPct !== null && Math.abs(token.discrepancyPct) > 10) tokenScore = 70;

    // Fingerprint score (0-100)
    const fingerprintScore = fingerprint.suspicious
        ? Math.max(20, 100 - fingerprint.confidence * 60)
        : 90;

    // Capability score (0-100)
    const capabilityScore = capability.passRate * 100;

    // Weighted average
    const overallScore = Math.round(
        latencyScore * 0.15 +
        tokenScore * 0.30 +
        fingerprintScore * 0.30 +
        capabilityScore * 0.25
    );

    // Trust level
    let trustLevel, trustColor, summary;
    if (overallScore >= 80) {
        trustLevel = '高信任度';
        trustColor = '#4ade80';
        summary = '各项检测均通过，未发现明显异常';
    } else if (overallScore >= 60) {
        trustLevel = '中等信任度';
        trustColor = '#fbbf24';
        summary = '部分检测存在异常，建议进一步验证';
    } else if (overallScore >= 40) {
        trustLevel = '低信任度';
        trustColor = '#f97316';
        summary = '多项检测存在异常，可能存在服务质量问题';
    } else {
        trustLevel = '严重可疑';
        trustColor = '#ef4444';
        summary = '检测到严重异常，强烈建议与官方API对比';
    }

    currentAudit.results.overall = {
        overallScore,
        trustLevel,
        trustColor,
        summary,
        latencyScore: Math.round(latencyScore),
        tokenScore,
        fingerprintScore: Math.round(fingerprintScore),
        capabilityScore: Math.round(capabilityScore),
    };

    updateProgress(100, '检测完成!');
}

// ─── API Call ──────────────────────────────────────────────────────────
async function makeApiCall(prompt, maxTokens = 64, temperature = 0) {
    const { apiKey, baseUrl, model } = currentAudit;
    const url = `${baseUrl.replace(/\/$/, '')}/chat/completions`;

    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
            model,
            messages: [{ role: 'user', content: prompt }],
            max_tokens: maxTokens,
            temperature,
        }),
    });

    if (!response.ok) {
        const errorText = await response.text();
        let errorMsg = `HTTP ${response.status}`;
        try {
            const errorJson = JSON.parse(errorText);
            errorMsg = errorJson.error?.message || errorMsg;
        } catch (e) { /* ignore */ }
        throw new Error(errorMsg);
    }

    return await response.json();
}

// ─── UI Helpers ────────────────────────────────────────────────────────
function showStep(stepId) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    $(stepId).classList.add('active');
}

function updateProgress(percent, text) {
    $('progressFill').style.width = `${percent}%`;
    $('progressText').textContent = text;
}

function updateStatus(elementId, status, text) {
    const el = $(elementId);
    el.className = `detail-status ${status}`;
    el.textContent = text;
}

function resetToInput() {
    showStep('step-input');
    updateProgress(0, '');
    ['latencyStatus', 'tokenStatus', 'fingerprintStatus', 'capabilityStatus'].forEach(id => {
        $(id).className = 'detail-status';
        $(id).textContent = '等待中...';
    });
}

// ─── Results Rendering ─────────────────────────────────────────────────
function renderResults() {
    const { overall, latency, token, fingerprint, capability } = currentAudit.results;

    // Score
    $('scoreNumber').textContent = overall.overallScore;
    $('trustLevel').textContent = overall.trustLevel;
    $('trustLevel').style.color = overall.trustColor;
    $('scoreSummary').textContent = overall.summary;

    // Update score circle color
    const scoreCircle = document.querySelector('.score-circle');
    scoreCircle.style.background = `conic-gradient(${overall.trustColor} 0deg, ${overall.trustColor} ${overall.overallScore * 3.6}deg, rgba(15, 23, 42, 0.8) ${overall.overallScore * 3.6}deg)`;

    // Latency
    $('latencyResult').innerHTML = `
        <p>平均延迟: <strong>${latency.avgLatency.toFixed(0)}ms</strong></p>
        <p>范围: ${latency.minLatency.toFixed(0)}ms - ${latency.maxLatency.toFixed(0)}ms</p>
        <p>评分: <span class="${overall.latencyScore >= 70 ? 'good' : overall.latencyScore >= 40 ? 'warning' : 'bad'}">${overall.latencyScore}/100</span></p>
    `;

    // Token
    let tokenHtml = `
        <p>报告 Prompt Tokens: <strong>${token.reportedPromptTokens}</strong></p>
    `;
    if (token.expectedPromptTokens !== null) {
        tokenHtml += `
            <p>预期 Prompt Tokens: ${token.expectedPromptTokens} (含chat template ${token.chatTemplateOverhead})</p>
            <p>差异率: <span class="${token.suspicious ? 'bad' : 'good'}">${token.discrepancyPct >= 0 ? '+' : ''}${token.discrepancyPct.toFixed(1)}%</span></p>
        `;
    } else {
        tokenHtml += '<p>预期 Tokens: 无法计算 (tiktoken未加载)</p>';
    }
    tokenHtml += `<p>评分: <span class="${token.tokenScore >= 70 ? 'good' : token.tokenScore >= 40 ? 'warning' : 'bad'}">${token.tokenScore}/100</span></p>`;
    if (token.discrepancyNote) {
        tokenHtml += `<p style="font-size:0.8rem;color:#64748b;margin-top:4px;">💡 ${token.discrepancyNote}</p>`;
    }
    $('tokenResult').innerHTML = tokenHtml;

    // Fingerprint
    $('fingerprintResult').innerHTML = `
        <p>Tokenizer探针: ${fingerprint.totalTokenizerProbes - fingerprint.tokenizerAnomalies}/${fingerprint.totalTokenizerProbes} 通过</p>
        <p>检测结果: <span class="${fingerprint.suspicious ? 'bad' : 'good'}">${fingerprint.detectedFamily}</span></p>
        <p>置信度: ${(fingerprint.confidence * 100).toFixed(0)}%</p>
        <p>评分: <span class="${overall.fingerprintScore >= 70 ? 'good' : overall.fingerprintScore >= 40 ? 'warning' : 'bad'}">${overall.fingerprintScore}/100</span></p>
    `;

    // Capability
    $('capabilityResult').innerHTML = `
        <p>通过: <strong>${capability.passed}/${capability.total}</strong> (${(capability.passRate * 100).toFixed(0)}%)</p>
        <p>模型等级估算: <span class="${capability.tierEstimate === 'high' ? 'good' : capability.tierEstimate === 'medium' ? 'warning' : 'bad'}">${capability.tierEstimate}</span></p>
        <p>评分: <span class="${overall.capabilityScore >= 70 ? 'good' : overall.capabilityScore >= 40 ? 'warning' : 'bad'}">${overall.capabilityScore}/100</span></p>
    `;

    // Show contribute button for deep mode
    $('contributeBtn').style.display = currentAudit.mode === 'deep' ? 'inline-block' : 'none';
}

// ─── History ───────────────────────────────────────────────────────────
function saveToHistory() {
    const history = JSON.parse(localStorage.getItem('transittruth_history') || '[]');
    const entry = {
        timestamp: new Date().toISOString(),
        baseUrl: currentAudit.baseUrl,
        model: currentAudit.model,
        score: currentAudit.results.overall.overallScore,
        trustLevel: currentAudit.results.overall.trustLevel,
    };
    history.unshift(entry);
    localStorage.setItem('transittruth_history', JSON.stringify(history.slice(0, 50)));
}

function loadHistory() {
    const history = JSON.parse(localStorage.getItem('transittruth_history') || '[]');
    const list = $('historyList');
    if (history.length === 0) {
        list.innerHTML = '<p style="color:#64748b;font-size:0.9rem;">暂无检测历史</p>';
        return;
    }
    list.innerHTML = history.slice(0, 10).map(h => {
        const date = new Date(h.timestamp).toLocaleString('zh-CN');
        const color = h.score >= 80 ? '#4ade80' : h.score >= 60 ? '#fbbf24' : h.score >= 40 ? '#f97316' : '#ef4444';
        return `
            <div class="history-item">
                <div class="history-info">
                    <span>${h.model}</span>
                    <span style="color:#64748b;font-size:0.8rem;">${h.baseUrl.substring(0, 30)}...</span>
                    <span style="color:#64748b;font-size:0.8rem;">${date}</span>
                </div>
                <span class="history-score" style="color:${color}">${h.score}</span>
            </div>
        `;
    }).join('');
}

// ─── Export ────────────────────────────────────────────────────────────
function exportReport() {
    const report = {
        tool: 'TransitTruth Pure Frontend Demo',
        version: '1.0.0',
        timestamp: new Date().toISOString(),
        audit: {
            baseUrl: currentAudit.baseUrl,
            model: currentAudit.model,
            mode: currentAudit.mode,
            durationMs: Date.now() - currentAudit.startTime,
        },
        results: currentAudit.results,
        disclaimer: '本报告由TransitTruth生成，基于有限样本，不构成对任何服务的最终评价。',
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transittruth_report_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ─── Contribute ────────────────────────────────────────────────────────
function contributeToRanking() {
    // Open GitHub issue template with pre-filled data
    const { baseUrl, model } = currentAudit;
    const { overallScore, trustLevel } = currentAudit.results.overall;
    const { discrepancyPct } = currentAudit.results.token;
    const { avgLatency } = currentAudit.results.latency;

    const title = encodeURIComponent(`[Audit Result] ${model} @ ${baseUrl}`);
    const body = encodeURIComponent(`
## 审计结果

- **中转站**: ${baseUrl}
- **模型**: ${model}
- **总体评分**: ${overallScore}/100
- **信任等级**: ${trustLevel}
- **Token差异率**: ${discrepancyPct !== null ? discrepancyPct.toFixed(1) + '%' : 'N/A'}
- **平均延迟**: ${avgLatency.toFixed(0)}ms

## 免责声明

此结果由用户使用TransitTruth工具生成，仅供参考。
    `.trim());

    window.open(`https://github.com/dafahaha/transit-truth/issues/new?template=audit_result.yml&title=${title}&body=${body}`, '_blank');
}

// ─── Utilities ─────────────────────────────────────────────────────────
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
