// TransitTruth - Frontend Application v0.2.0

const API_BASE = '';
const STORAGE_KEY = 'transittruth_history';

// ===== Tab Navigation =====
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const tab = link.dataset.tab;
        switchTab(tab);
    });
});

function switchTab(tab) {
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-link[data-tab="${tab}"]`).classList.add('active');
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');

    if (tab === 'ranking') loadRanking();
    if (tab === 'history') loadHistory();
}

// ===== Step-based Form Flow =====
const apiKeyInput = document.getElementById('apiKey');
const baseUrlInput = document.getElementById('baseUrl');
const modelSelect = document.getElementById('modelSelect');
const modelManual = document.getElementById('modelManual');
const submitBtn = document.getElementById('submitBtn');
const fetchModelsBtn = document.getElementById('fetchModelsBtn');

let detectedModels = [];
let currentAuditResult = null;

// Step 1: API Key input -> auto detect
let detectTimeout = null;
apiKeyInput.addEventListener('input', () => {
    const key = apiKeyInput.value.trim();
    if (key.length < 5) {
        hideDetectStatus();
        return;
    }
    // Debounce detection
    clearTimeout(detectTimeout);
    showDetectStatus('正在自动检测中转站...');
    detectTimeout = setTimeout(() => detectRelay(key), 800);
});

async function detectRelay(apiKey) {
    try {
        const response = await fetch(`${API_BASE}/api/detect/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey }),
        });
        const data = await response.json();

        if (data.detected_base_url) {
            baseUrlInput.value = data.detected_base_url;
            showDetectStatus(`✓ 自动检测到: ${data.detected_base_url}`, 'success');
            showStep('step-url');
        } else if (data.suggestions && data.suggestions.length > 0) {
            showUrlSuggestions(data.suggestions);
            showDetectStatus('请选择或手动输入 Base URL', 'warning');
            showStep('step-url');
        } else {
            showDetectStatus('无法自动检测，请手动输入 Base URL', 'warning');
            showStep('step-url');
        }
    } catch (err) {
        showDetectStatus('检测失败，请手动输入 Base URL', 'error');
        showStep('step-url');
    }
}

function showUrlSuggestions(suggestions) {
    const container = document.getElementById('urlSuggestions');
    container.innerHTML = '';
    suggestions.forEach(s => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'url-suggestion-btn';
        btn.innerHTML = `<strong>${s.name}</strong> <span class="url">${s.base_url}</span> <span class="confidence">${Math.round(s.confidence * 100)}%</span>`;
        btn.addEventListener('click', () => {
            baseUrlInput.value = s.base_url;
            container.innerHTML = '';
        });
        container.appendChild(btn);
    });
}

// Step 2: Fetch models
fetchModelsBtn.addEventListener('click', async () => {
    const apiKey = apiKeyInput.value.trim();
    const baseUrl = baseUrlInput.value.trim();
    if (!apiKey || !baseUrl) {
        alert('请先输入 API Key 和 Base URL');
        return;
    }

    fetchModelsBtn.disabled = true;
    fetchModelsBtn.textContent = '获取中...';

    try {
        const response = await fetch(`${API_BASE}/api/detect/models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, base_url: baseUrl }),
        });
        const data = await response.json();

        if (data.available && data.models.length > 0) {
            detectedModels = data.models;
            modelSelect.innerHTML = '<option value="">-- 选择模型 --</option>';
            data.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modelSelect.appendChild(opt);
            });
            showStep('step-model');
            fetchModelsBtn.textContent = '✓ 已获取模型列表';
        } else {
            alert('无法获取模型列表（/models 端点不可用），请手动输入模型名称');
            showStep('step-model');
            fetchModelsBtn.textContent = '重新获取';
        }
    } catch (err) {
        alert(`获取模型失败: ${err.message}`);
        fetchModelsBtn.textContent = '重新获取';
    } finally {
        fetchModelsBtn.disabled = false;
        checkSubmitReady();
    }
});

// Model selection
modelSelect.addEventListener('change', checkSubmitReady);
modelManual.addEventListener('input', checkSubmitReady);

// Mode toggle
document.querySelectorAll('input[name="mode"]').forEach(radio => {
    radio.addEventListener('change', () => {
        document.querySelectorAll('.mode-option').forEach(opt => opt.classList.remove('selected'));
        radio.closest('.mode-option').classList.add('selected');
    });
});

function getSelectedModel() {
    return modelSelect.value || modelManual.value.trim();
}

function checkSubmitReady() {
    const apiKey = apiKeyInput.value.trim();
    const baseUrl = baseUrlInput.value.trim();
    const model = getSelectedModel();
    submitBtn.disabled = !(apiKey && baseUrl && model);
}

function showStep(stepId) {
    document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
    document.getElementById(stepId).classList.add('active');
}

function showDetectStatus(text, type = 'info') {
    const status = document.getElementById('detectStatus');
    const textEl = document.getElementById('detectText');
    status.style.display = 'flex';
    status.className = `detect-status ${type}`;
    textEl.textContent = text;
}

function hideDetectStatus() {
    document.getElementById('detectStatus').style.display = 'none';
}

// ===== Audit Submission =====
submitBtn.addEventListener('click', async () => {
    const apiKey = apiKeyInput.value.trim();
    const baseUrl = baseUrlInput.value.trim();
    const model = getSelectedModel();
    const officialKey = document.getElementById('officialKey').value.trim();
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const checks = Array.from(document.querySelectorAll('input[name="checks"]:checked')).map(c => c.value);

    if (!apiKey || !baseUrl || !model) {
        alert('请填写完整信息');
        return;
    }

    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');

    submitBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';

    // Show progress
    document.getElementById('progressSection').style.display = 'block';
    updateProgress(10, '正在连接 API...');

    try {
        updateProgress(20, '正在检测 API 可用性...');

        const response = await fetch(`${API_BASE}/api/audit/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                base_url: baseUrl,
                model: model,
                official_api_key: officialKey || null,
                mode: mode,
                run_token_check: checks.includes('token'),
                run_fingerprint: checks.includes('fingerprint'),
                run_latency: checks.includes('latency'),
                run_protocol: checks.includes('protocol'),
            }),
        });

        updateProgress(80, '正在分析结果...');
        const result = await response.json();

        if (result.status === 'failed') {
            alert(`审计失败: ${result.error || '未知错误'}`);
            document.getElementById('progressSection').style.display = 'none';
        } else {
            updateProgress(100, '审计完成！');
            currentAuditResult = result;
            displayResults(result);
            saveToHistory(result);
        }
    } catch (err) {
        alert(`请求失败: ${err.message}`);
        document.getElementById('progressSection').style.display = 'none';
    } finally {
        submitBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
});

function updateProgress(percent, text) {
    document.getElementById('progressFill').style.width = `${percent}%`;
    document.getElementById('progressText').textContent = text;
}

// ===== Results Display =====
function displayResults(result) {
    document.getElementById('results').style.display = 'block';
    document.getElementById('auditId').textContent = `Audit ID: ${result.audit_id}`;

    const score = Math.round(result.overall_score);
    document.getElementById('scoreValue').textContent = score;
    document.getElementById('scoreModel').textContent = result.model;
    document.getElementById('scoreUrl').textContent = result.base_url;

    const trustLevel = result.trust_level;
    const trustEl = document.getElementById('trustLevel');
    const scoreCircle = document.querySelector('.score-circle');
    trustEl.textContent = getTrustLabel(trustLevel);
    trustEl.className = `trust-level ${trustLevel}`;
    scoreCircle.className = `score-circle ${trustLevel}`;

    // Checks
    const checksList = document.getElementById('checksList');
    checksList.innerHTML = '';
    result.checks.forEach(check => {
        const item = document.createElement('div');
        item.className = 'check-item';
        const passed = check.passed;
        item.innerHTML = `
            <div class="check-icon ${passed ? 'pass' : 'fail'}">${passed ? '✓' : '✗'}</div>
            <div class="check-content">
                <div class="check-name">${check.name}</div>
                <div class="check-details">${check.details}</div>
            </div>
            <div class="check-score ${passed ? 'pass' : 'fail'}">${Math.round(check.score)}</div>
        `;
        checksList.appendChild(item);
    });

    // Summary
    document.getElementById('summaryText').textContent = result.summary;

    // Recommendations
    const recList = document.getElementById('recommendationsList');
    recList.innerHTML = '';
    result.recommendations.forEach(rec => {
        const li = document.createElement('li');
        li.textContent = rec;
        recList.appendChild(li);
    });

    // Show contribute section (only for deep mode)
    const mode = document.querySelector('input[name="mode"]:checked').value;
    document.getElementById('contributeSection').style.display = mode === 'deep' ? 'block' : 'none';

    // Scroll to results
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

function getTrustLabel(level) {
    const labels = {
        high: '高信任度',
        medium: '中等信任',
        low: '低信任度',
        critical: '危险',
        unknown: '未知',
    };
    return labels[level] || level;
}

// ===== Contribute to Ranking =====
document.getElementById('contributeBtn').addEventListener('click', () => {
    if (!currentAuditResult) return;

    const isAnonymous = document.querySelector('input[name="contributeAnon"]:checked').value === 'anonymous';
    const resultEl = document.getElementById('contributeResult');

    // Generate GitHub Issue content
    const issueContent = generateIssueContent(currentAuditResult, isAnonymous);
    const issueTitle = `[Audit] ${extractRelayName(currentAuditResult.base_url)} - ${currentAuditResult.model} - ${Math.round(currentAuditResult.overall_score)}/100`;

    // Open GitHub new issue page with prefilled content
    const githubUrl = `https://github.com/dafahaha/transit-truth/issues/new?title=${encodeURIComponent(issueTitle)}&body=${encodeURIComponent(issueContent)}&labels=audit-result`;

    resultEl.style.display = 'block';
    resultEl.innerHTML = `
        <p>✅ 已生成贡献内容！点击下方按钮在 GitHub 上提交：</p>
        <a href="${githubUrl}" target="_blank" class="btn btn-primary btn-small">📝 在 GitHub 上提交 Issue</a>
        <p style="margin-top:8px;font-size:12px;color:#666;">提交后，你的审计结果将经过社区验证后加入排行榜。</p>
    `;
});

function generateIssueContent(result, isAnonymous) {
    const tc = result.token_comparison || {};
    const fp = result.fingerprint || {};
    const contributor = isAnonymous ? '匿名' : '@dafahaha (请替换为你的GitHub用户名)';

    return `---
audit_id: ${result.audit_id}
relay: ${extractRelayName(result.base_url)}
base_url: ${result.base_url}
model: ${result.model}
overall_score: ${result.overall_score}
trust_level: ${result.trust_level}
token_inflation_pct: ${tc.prompt_inflation_pct || 'N/A'}
avg_latency_ms: ${result.checks.find(c => c.check_type === 'response_latency')?.evidence?.avg_latency_ms || 'N/A'}
fingerprint_family: ${fp.detected_family || 'N/A'}
fingerprint_match: ${fp.family_match || 'N/A'}
tested_at: ${result.completed_at || new Date().toISOString()}
contributor: ${contributor}
mode: deep
---

## 审计摘要

${result.summary}

## 检测详情

| 检测项 | 得分 | 状态 | 详情 |
|---|---|---|---|
${result.checks.map(c => `| ${c.name} | ${Math.round(c.score)}/100 | ${c.passed ? '✅ 通过' : '❌ 未通过'} | ${c.details} |`).join('\n')}

## Token 对比

- 报告 Prompt Tokens: ${tc.prompt_tokens_reported || 'N/A'}
- 预期 Prompt Tokens: ${tc.prompt_tokens_expected || 'N/A'}
- 差异率: ${tc.prompt_inflation_pct ? tc.prompt_inflation_pct + '%' : 'N/A'}
- Chat Template 估算: ${tc.chat_template_overhead || 0} tokens
- 可疑: ${tc.suspicious ? '是（已扣除chat template）' : '否'}
${tc.discrepancy_note ? '- 说明: ' + tc.discrepancy_note : ''}

## 模型指纹

- 声称模型: ${fp.claimed_model || 'N/A'}
- 检测家族: ${fp.detected_family || 'N/A'}
- 家族匹配: ${fp.family_match ? '是' : '否'}
- 置信度: ${fp.confidence ? Math.round(fp.confidence * 100) + '%' : 'N/A'}

## 建议

${result.recommendations.map(r => `- ${r}`).join('\n')}

---
*本结果由 TransitTruth 自动生成，仅供参考。*
`;
}

function extractRelayName(baseUrl) {
    try {
        const url = new URL(baseUrl);
        return url.hostname;
    } catch {
        return baseUrl;
    }
}

// ===== Local History =====
function saveToHistory(result) {
    try {
        const history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        history.unshift({
            audit_id: result.audit_id,
            model: result.model,
            base_url: result.base_url,
            overall_score: result.overall_score,
            trust_level: result.trust_level,
            started_at: result.started_at,
            result_json: JSON.stringify(result),
        });
        // Keep only last 50
        localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, 50)));
    } catch (e) {
        console.error('Failed to save history:', e);
    }
}

function loadHistory() {
    const container = document.getElementById('historyList');
    try {
        const history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        if (history.length === 0) {
            container.innerHTML = '<p class="empty-text">暂无审计记录</p>';
            return;
        }

        let html = '';
        history.forEach(a => {
            const level = getScoreLevel(a.overall_score);
            const date = new Date(a.started_at).toLocaleString();
            html += `<div class="history-item" data-id="${a.audit_id}">
                <div class="history-model">${a.model}</div>
                <div class="history-url">${a.base_url}</div>
                <div class="history-score ${level}">${Math.round(a.overall_score)}</div>
                <div class="history-date">${date}</div>
            </div>`;
        });
        container.innerHTML = html;

        // Click to view details
        document.querySelectorAll('.history-item').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.id;
                const history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
                const record = history.find(h => h.audit_id === id);
                if (record && record.result_json) {
                    currentAuditResult = JSON.parse(record.result_json);
                    displayResults(currentAuditResult);
                    switchTab('audit');
                }
            });
        });
    } catch (err) {
        container.innerHTML = `<p class="empty-text">加载失败: ${err.message}</p>`;
    }
}

// ===== Ranking (GitHub Issues based) =====
async function loadRanking() {
    const container = document.getElementById('rankingTable');
    container.innerHTML = '<p class="loading-text">加载中...</p>';

    try {
        // Fetch audit issues from GitHub
        const response = await fetch(
            'https://api.github.com/repos/dafahaha/transit-truth/issues?labels=audit-result&state=open&per_page=100'
        );

        if (!response.ok) {
            throw new Error(`GitHub API error: ${response.status}`);
        }

        const issues = await response.json();

        if (issues.length === 0) {
            container.innerHTML = `
                <p class="empty-text">暂无排行榜数据</p>
                <p style="text-align:center;color:#666;">完成一次深度审计后，点击"贡献到排行榜"即可添加数据。</p>
            `;
            return;
        }

        // Parse issues and build ranking
        const entries = issues.map(issue => parseAuditIssue(issue)).filter(e => e);

        // Populate filters
        populateRankingFilters(entries);

        // Apply filters
        const filtered = applyRankingFilters(entries);

        // Sort by score descending
        filtered.sort((a, b) => b.overall_score - a.overall_score);

        // Render table
        let html = '<table><thead><tr>';
        html += '<th>#</th><th>中转站</th><th>模型</th><th>信任分</th><th>Token差异率</th><th>平均延迟</th><th>贡献者</th><th>审计时间</th>';
        html += '</tr></thead><tbody>';

        filtered.forEach((r, i) => {
            const level = getScoreLevel(r.overall_score);
            html += `<tr>
                <td>${i + 1}</td>
                <td><strong>${r.relay}</strong></td>
                <td>${r.model}</td>
                <td><span class="score-badge ${level}">${Math.round(r.overall_score)}</span></td>
                <td>${r.token_inflation_pct !== 'N/A' ? r.token_inflation_pct + '%' : '-'}</td>
                <td>${r.avg_latency_ms !== 'N/A' ? Math.round(r.avg_latency_ms) + 'ms' : '-'}</td>
                <td>${r.contributor || '-'}</td>
                <td>${r.tested_at ? new Date(r.tested_at).toLocaleDateString() : '-'}</td>
            </tr>`;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = `
            <p class="empty-text">排行榜加载中...</p>
            <p style="text-align:center;color:#666;font-size:12px;">排行榜基于 GitHub Issues，首次加载可能需要几秒。</p>
            <p style="text-align:center;color:#999;font-size:11px;">${err.message}</p>
        `;
    }
}

function parseAuditIssue(issue) {
    try {
        // Parse frontmatter from issue body
        const body = issue.body || '';
        const frontmatterMatch = body.match(/^---\n([\s\S]*?)\n---/);
        if (!frontmatterMatch) return null;

        const fm = {};
        frontmatterMatch[1].split('\n').forEach(line => {
            const [key, ...valueParts] = line.split(':');
            if (key && valueParts.length > 0) {
                fm[key.trim()] = valueParts.join(':').trim();
            }
        });

        return {
            relay: fm.relay || 'unknown',
            base_url: fm.base_url || '',
            model: fm.model || 'unknown',
            overall_score: parseFloat(fm.overall_score) || 0,
            trust_level: fm.trust_level || 'unknown',
            token_inflation_pct: fm.token_inflation_pct || 'N/A',
            avg_latency_ms: fm.avg_latency_ms !== 'N/A' ? parseFloat(fm.avg_latency_ms) : 'N/A',
            contributor: fm.contributor || '',
            tested_at: fm.tested_at || '',
            issue_url: issue.html_url,
        };
    } catch {
        return null;
    }
}

function populateRankingFilters(entries) {
    const relaySelect = document.getElementById('rankingFilterRelay');
    const modelSelect = document.getElementById('rankingFilterModel');

    const relays = [...new Set(entries.map(e => e.relay))];
    const models = [...new Set(entries.map(e => e.model))];

    relaySelect.innerHTML = '<option value="">全部中转站</option>';
    relays.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r;
        opt.textContent = r;
        relaySelect.appendChild(opt);
    });

    modelSelect.innerHTML = '<option value="">全部模型</option>';
    models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        modelSelect.appendChild(opt);
    });
}

function applyRankingFilters(entries) {
    const relay = document.getElementById('rankingFilterRelay').value;
    const model = document.getElementById('rankingFilterModel').value;
    const trust = document.getElementById('rankingFilterTrust').value;

    return entries.filter(e => {
        if (relay && e.relay !== relay) return false;
        if (model && e.model !== model) return false;
        if (trust && e.trust_level !== trust) return false;
        return true;
    });
}

document.getElementById('refreshRanking').addEventListener('click', loadRanking);
document.getElementById('rankingFilterRelay').addEventListener('change', loadRanking);
document.getElementById('rankingFilterModel').addEventListener('change', loadRanking);
document.getElementById('rankingFilterTrust').addEventListener('change', loadRanking);

function getScoreLevel(score) {
    if (score >= 80) return 'high';
    if (score >= 60) return 'medium';
    if (score >= 40) return 'low';
    return 'critical';
}

// ===== Initialize =====
console.log('TransitTruth v0.2.0 frontend loaded');
