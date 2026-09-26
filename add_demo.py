import io

path = r"D:\github项目\transit-truth\index.html"
with io.open(path, "r", encoding="utf-8", newline="") as f:
    content = f.read()

# 1. 加演示按钮
old_btn = """    <button class="btn" id="start-btn" onclick="startAudit()">\U0001F680 \u5f00\u59cb\u5ba1\u8ba1</button>
  </div>"""
new_btn = """    <div class="btn-row">
      <button class="btn" id="start-btn" onclick="startAudit()">\U0001F680 \u5f00\u59cb\u5ba1\u8ba1</button>
      <button class="btn btn-demo" id="demo-btn" onclick="runDemo()">\U0001F3AC \u5148\u770b\u6f14\u793a\uff08\u65e0\u9700 Key\uff09</button>
    </div>
  </div>"""
assert old_btn in content, "btn block not found"
content = content.replace(old_btn, new_btn)

# 2. 在 startAudit 函数前插入 runDemo 函数
demo_func = """
// \u2500\u2500\u2500 \u6f14\u793a\u6a21\u5f0f\uff08\u65e0\u9700 API Key\uff09 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
async function runDemo() {
  const btn = document.getElementById('demo-btn');
  const progressContainer = document.getElementById('progress-container');
  const resultCard = document.getElementById('result-card');

  btn.disabled = true;
  btn.textContent = '\u6f14\u793a\u4e2d...';
  resultCard.classList.add('hidden');
  progressContainer.style.display = 'block';

  // \u6f14\u793a\u573a\u666f\uff1a\u58f0\u79f0 gpt-4o \u4f46\u53d1\u73b0\u964d\u7ea7\u8ff9\u8c61
  const demoSteps = [
    [10, '\u6b63\u5728\u8fdb\u884c Token \u8ba1\u6570\u9a8c\u8bc1...'],
    [30, '\u6b63\u5728\u8fd0\u884c\u6a21\u578b\u6307\u7eb9\u63a2\u9488...'],
    [70, '\u6b63\u5728\u68c0\u6d4b\u5ef6\u8fdf\u548c\u534f\u8bae...'],
    [90, '\u6b63\u5728\u8ba1\u7b97\u5ba1\u8ba1\u7ed3\u679c...'],
  ];
  for (const [pct, txt] of demoSteps) {
    updateProgress(pct, txt);
    await sleep(900);
  }

  // \u6784\u9020\u6a21\u62df\u5ba1\u8ba1\u7ed3\u679c\uff08\u53ef\u7591\u4e2d\u8f6c\u7ad9\u573a\u666f\uff09
  auditResult = {
    model: 'gpt-4o',
    base_url: 'https://demo-relay.example.com/v1',
    relay_name: '\u6f14\u793a\u4e2d\u8f6c\u7ad9',
    mode: 'quick',
    timestamp: new Date().toISOString(),
    duration_ms: 3600,
    checks: [
      {
        name: 'Token \u8ba1\u6570\u9a8c\u8bc1',
        score: 30,
        passed: false,
        details: '\u5b9e\u9645\u9884\u671f 34 tokens\uff0c\u4e2d\u8f6c\u7ad9\u62a5\u5442 42 tokens\uff0c\u5dee\u5f02\u7387 +23.5%\uff08\u6263\u9664 chat template \u540e\u4ecd\u7591\u4f3c\u865a\u9ad8\uff09',
      },
      {
        name: '\u6a21\u578b\u6307\u7eb9\u68c0\u6d4b',
        score: 35,
        passed: false,
        details: '\u884c\u4e3a\u6307\u7eb9\u66f4\u63a5\u8fd1 gpt-4o-mini \u7684\u5206\u5e03\u7279\u5f81\uff08\u968f\u673a\u6570\u504f\u597d 7\u7684\u6982\u7387\u663e\u8457\u4f4e\u4e8e gpt-4o \u57fa\u51c6\uff09\uff0c\u5bb6\u65cf\u5339\u914d\u5931\u8d25\uff0c\u7f6e\u4fe1\u5ea6 82%',
      },
      {
        name: '\u5ef6\u8fdf\u4e0e\u534f\u8bae',
        score: 70,
        passed: true,
        details: '\u5e73\u5747\u5ef6\u8fdf 1240ms\uff08\u504f\u6162\uff09\uff1bOpenAI \u534f\u8bae\u517c\u5bb9\u3001Usage \u8fd4\u56de\u3001Model \u56de\u663e\u5747\u6b63\u5e38',
      },
    ],
    token_comparison: {
      prompt_tokens_reported: 42,
      prompt_tokens_expected: 34,
      chat_template_overhead: 0,
      prompt_inflation_pct: 23.5,
      suspicious: true,
      discrepancy_note: '\u6f14\u793a\u6570\u636e\uff1a\u5df2\u6263\u9664 chat template \u5f00\u9500\u540e\u4ecd\u5b58\u5728\u5dee\u5f02\uff0c\u53ef\u7591',
    },
    fingerprint: {
      claimed_model: 'gpt-4o',
      detected_family: 'openai-gpt\uff08\u504f\u5411 gpt-4o-mini \u7279\u5f81\uff09',
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
  updateProgress(100, '\u5ba1\u8ba1\u5b8c\u6210\uff01\uff08\u6f14\u793a\u6570\u636e\uff09');
  await sleep(500);
  progressContainer.style.display = 'none';
  showResult();

  btn.disabled = false;
  btn.textContent = '\U0001F3AC \u5148\u770b\u6f14\u793a\uff08\u65e0\u9700 Key\uff09';
}

async function startAudit() {"""
old_start = "async function startAudit() {"
assert old_start in content, "startAudit not found"
content = content.replace(old_start, demo_func, 1)

with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(content)
print("OK: 演示模式已插入")
