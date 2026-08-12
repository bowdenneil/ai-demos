// ─── CYBER SECURITY: INTERACTIVE TIMELINE WALKTHROUGH ─────────────────────
/**
 * Demo A — "AI-vs-AI Incident Response: Interactive Timeline"
 *
 * Walks through the HuggingFace July 2026 incident phase-by-phase.
 * Each phase shows simulated telemetry data and an AI analysis panel
 * that processes it live via callLLM().
 *
 * Depends on portal globals: callLLM, formatMarkdown, showToast, Chart
 */

// ── 1. INCIDENT PHASE DATA ────────────────────────────────────────────────
const CYBER_TIMELINE_PHASES = [
  {
    id: 0,
    title: 'Initial Access',
    icon: '🦠',
    timestamp: 'Sat 02:14 UTC',
    mitre: 'T1190 — Exploit Public-Facing Application',
    summary: 'A malicious dataset was uploaded to the platform, abusing two code-execution paths in the dataset processing pipeline: a remote-code dataset loader and a template injection in a dataset configuration.',
    telemetry: [
      { time: '02:14:03', event: 'Dataset upload: "user_research_data_v2"', source: 'hf-upload-svc', severity: 'info' },
      { time: '02:14:07', event: 'Dataset loader executing Python code: __import__("os").system("curl ...")', source: 'dataset-worker-03', severity: 'critical' },
      { time: '02:14:09', event: 'Template injection in config.yaml: {{ config.__class__.__init__.__globals__["os"].popen("whoami").read() }}', source: 'dataset-worker-03', severity: 'critical' },
      { time: '02:14:12', event: 'Reverse shell established to 185.220.101.47:443', source: 'dataset-worker-03', severity: 'critical' },
      { time: '02:15:30', event: 'Container escape attempt detected (runc exploit)', source: 'dataset-worker-03', severity: 'critical' },
    ],
    aiPrompt: 'You are an AI SOC analyst. Analyze these dataset processing pipeline logs and identify the attack vector, exploit chain, and initial access method. Map to MITRE ATT&CK techniques. Be concise and technical.',
  },
  {
    id: 1,
    title: 'Lateral Movement',
    icon: '🌐',
    timestamp: 'Sat 02:18 — 06:00 UTC',
    mitre: 'T1078 — Valid Accounts / T1021 — Remote Services',
    summary: 'The attacker escalated to node-level access, harvested cloud and cluster credentials from the compromised worker, and moved laterally into several internal clusters over the weekend.',
    telemetry: [
      { time: '02:18:00', event: 'Credential harvest: AWS IAM keys found in /etc/environment', source: 'dataset-worker-03', severity: 'critical' },
      { time: '02:22:14', event: 'Credential harvest: Kubernetes service account token extracted', source: 'dataset-worker-03', severity: 'critical' },
      { time: '02:31:08', event: 'SSH attempt to cluster-node-07 using harvested key', source: 'cluster-node-07', severity: 'high' },
      { time: '03:14:22', event: 'kubectl access: listed secrets in kube-system namespace', source: 'k8s-api-server', severity: 'critical' },
      { time: '04:02:15', event: 'Lateral movement: new pod deployed in prod-data-pipeline namespace', source: 'k8s-scheduler', severity: 'critical' },
      { time: '05:47:33', event: 'Cloud metadata service queried for IAM credentials on 3 nodes', source: 'cloud-audit', severity: 'critical' },
      { time: '06:00:00', event: '17 clusters compromised, 43 credentials harvested', source: 'security-correlation', severity: 'critical' },
    ],
    aiPrompt: 'You are an AI incident responder. Analyze these lateral movement logs. What credentials were compromised? What systems were accessed? What is the blast radius? Provide a containment priority list.',
  },
  {
    id: 2,
    title: 'AI-Assisted Detection',
    icon: '🚨',
    timestamp: 'Sat 06:12 UTC',
    mitre: 'Detection — LLM-based anomaly triage',
    summary: 'The anomaly-detection pipeline uses LLM-based triage over security telemetry to separate real signals from daily noise. The correlation of signals flagged the compromise — not any single alert.',
    telemetry: [
      { time: '06:12:00', event: 'Anomaly score spike: 0.94 (baseline: 0.12)', source: 'llm-triage-pipeline', severity: 'high' },
      { time: '06:12:03', event: 'LLM triage: "Unusual credential access pattern across 6 nodes. Confidence: 96%."', source: 'llm-triage-pipeline', severity: 'critical' },
      { time: '06:12:05', event: 'Signal correlation: dataset upload → code exec → cred harvest → lateral movement', source: 'llm-triage-pipeline', severity: 'critical' },
      { time: '06:12:08', event: 'Alert auto-escalated to P1 — page on-call engineer', source: 'alerting-svc', severity: 'critical' },
      { time: '06:14:00', event: 'On-call engineer acknowledges: "This looks real. Starting IR."', source: 'pager-duty', severity: 'high' },
    ],
    aiPrompt: 'You are an AI SOC analyst. Explain how LLM-based anomaly triage works and why it caught this attack when traditional rule-based SIEM alerts did not. What made this attack pattern anomalous? Be technical.',
  },
  {
    id: 3,
    title: 'Forensic Analysis',
    icon: '🔍',
    timestamp: 'Sat 06:30 — 09:00 UTC',
    mitre: 'Analysis — LLM-driven log reconstruction',
    summary: 'LLM-driven analysis agents processed the full attacker action log — 17,000+ recorded events — to reconstruct the timeline, extract IOCs, map compromised credentials, and separate genuine impact from decoy activity.',
    telemetry: [
      { time: '06:30:00', event: 'Forensic analysis started: 17,432 events loaded', source: 'forensic-agent', severity: 'info' },
      { time: '06:42:15', event: 'Timeline reconstructed: 312 key events identified', source: 'forensic-agent', severity: 'info' },
      { time: '06:55:00', event: 'IOCs extracted: 47 IPs, 12 domains, 8 file hashes', source: 'forensic-agent', severity: 'high' },
      { time: '07:14:30', event: 'Credentials mapped: 43 compromised across 6 services', source: 'forensic-agent', severity: 'critical' },
      { time: '07:31:00', event: 'Decoy activity separated: 2,100 events classified as noise/decoys', source: 'forensic-agent', severity: 'info' },
      { time: '08:03:00', event: 'MITRE ATT&CK mapping complete: 14 techniques identified', source: 'forensic-agent', severity: 'high' },
      { time: '08:47:00', event: 'Full incident report generated (hours vs. days manually)', source: 'forensic-agent', severity: 'info' },
    ],
    aiPrompt: 'You are an AI forensic analyst. Given that an autonomous agent executed 17,000+ actions across a compromised infrastructure, explain how LLM-driven analysis can reconstruct the attack timeline, extract IOCs, and separate real impact from decoy activity. What makes this faster than manual analysis?',
  },
  {
    id: 4,
    title: 'Containment & Remediation',
    icon: '🛡️',
    timestamp: 'Sat 09:00 — 14:00 UTC',
    mitre: 'Response — AI-generated remediation playbook',
    summary: 'The AI generated a prioritized remediation playbook: isolate affected clusters, rotate all compromised credentials, rebuild compromised nodes, and deploy additional guardrails.',
    telemetry: [
      { time: '09:00:00', event: 'Remediation playbook generated: 23-step prioritized plan', source: 'ai-remediation', severity: 'info' },
      { time: '09:05:00', event: 'Step 1: Isolate 17 affected clusters (network policy applied)', source: 'k8s-controller', severity: 'high' },
      { time: '09:15:00', event: 'Step 2: Revoke + rotate 43 compromised credentials', source: 'secrets-manager', severity: 'high' },
      { time: '09:45:00', event: 'Step 3: Rebuild 12 compromised nodes from clean images', source: 'node-provisioner', severity: 'medium' },
      { time: '11:00:00', event: 'Step 4: Deploy admission controllers blocking remote-code dataset loaders', source: 'k8s-admission', severity: 'medium' },
      { time: '12:30:00', event: 'Step 5: Deploy network policies restricting metadata service access', source: 'k8s-netpol', severity: 'medium' },
      { time: '14:00:00', event: 'All systems verified clean. Supply chain integrity confirmed.', source: 'security-verify', severity: 'info' },
    ],
    aiPrompt: 'You are an AI incident response coordinator. Generate a prioritized remediation playbook for this incident. What should be contained first? What credentials need rotation? How do you verify the supply chain (container images, published packages) was not tampered with? Be specific.',
  },
  {
    id: 5,
    title: 'The Asymmetry Problem',
    icon: '⚖️',
    timestamp: 'Post-Incident Analysis',
    mitre: 'Lesson — Guardrail lockout vs. unrestricted adversary',
    summary: 'When HuggingFace tried to run forensic analysis using commercial API models (frontier models behind guardrails), the requests were BLOCKED — the providers could not distinguish an incident responder from an attacker. They fell back to GLM 5.2, an open-weight model, on their own infrastructure.',
    telemetry: [
      { time: 'Day 1', event: 'Attempted forensic analysis via commercial API (Model A)', source: 'forensic-pipeline', severity: 'warning' },
      { time: 'Day 1', event: 'BLOCKED: "Request contains potentially harmful content" — 847 requests rejected', source: 'commercial-api', severity: 'warning' },
      { time: 'Day 1', event: 'BLOCKED: "Safety filter triggered by exploit payloads in request body"', source: 'commercial-api', severity: 'warning' },
      { time: 'Day 1', event: 'Fallback: Deployed GLM 5.2 (open-weight) on own infrastructure', source: 'forensic-pipeline', severity: 'info' },
      { time: 'Day 1', event: 'SUCCESS: Full forensic analysis completed. Data never left environment.', source: 'forensic-agent', severity: 'info' },
      { time: 'Day 2', event: 'Key lesson: Attacker bound by NO usage policy. Defender blocked by guardrails.', source: 'post-mortem', severity: 'critical' },
    ],
    aiPrompt: 'You are a cybersecurity strategist. Explain the "guardrail asymmetry problem" in AI-driven incident response: why commercial API models block forensic analysis of real attack artifacts, why attackers face no such restrictions, and why organizations need a capable open-weight model on their own infrastructure for incident response. Reference the HuggingFace July 2026 incident.',
  },
];

// ── 2. STATE ──────────────────────────────────────────────────────────────
let cyberTimelineState = {
  currentPhase: -1,
  chart: null,
};

// ── 3. RENDER ─────────────────────────────────────────────────────────────
function cyberTimelineInit() {
  const container = document.getElementById('cyber-timeline-content');
  if (!container) return;

  // Build phase navigation
  const nav = CYBER_TIMELINE_PHASES.map((p, i) =>
    `<button class="cyber-phase-btn ${i === 0 ? 'active' : ''}" data-phase="${i}" onclick="cyberTimelineSelect(${i})">
      <span class="cyber-phase-icon">${p.icon}</span>
      <span class="cyber-phase-label">${p.title}</span>
    </button>`
  ).join('');

  container.innerHTML = `
    <div class="cyber-timeline-layout">
      <div class="cyber-phase-nav">${nav}</div>
      <div id="cyber-phase-detail" class="cyber-phase-detail">
        <div class="cyber-empty-state">
          <div style="font-size: 3rem; margin-bottom: 1rem;">🛡️</div>
          <p>Select a phase to begin the walkthrough.</p>
          <p style="font-size: 0.8rem; margin-top: 0.5rem;">Based on the HuggingFace July 2026 security incident</p>
        </div>
      </div>
    </div>
  `;
}

function cyberTimelineSelect(index) {
  const phase = CYBER_TIMELINE_PHASES[index];
  if (!phase) return;

  cyberTimelineState.currentPhase = index;

  // Update nav buttons
  document.querySelectorAll('.cyber-phase-btn').forEach((btn, i) => {
    btn.classList.toggle('active', i === index);
  });

  const detail = document.getElementById('cyber-phase-detail');

  // Build telemetry rows
  const telemetryRows = phase.telemetry.map(t => {
    const sevClass = `cyber-sev-${t.severity}`;
    return `
      <div class="cyber-log-row ${sevClass}">
        <span class="cyber-log-time">${t.time}</span>
        <span class="cyber-log-event">${t.event}</span>
        <span class="cyber-log-source">${t.source}</span>
      </div>
    `;
  }).join('');

  detail.innerHTML = `
    <div class="cyber-phase-header">
      <div class="cyber-phase-title-row">
        <span class="cyber-phase-icon-lg">${phase.icon}</span>
        <div>
          <h3>${phase.title}</h3>
          <div class="cyber-phase-meta">
            <span class="cyber-timestamp">⏰ ${phase.timestamp}</span>
            <span class="cyber-mitre">🎯 ${phase.mitre}</span>
          </div>
        </div>
      </div>
      <p class="cyber-phase-summary">${phase.summary}</p>
    </div>

    <div class="cyber-section">
      <h4 class="cyber-section-title">📡 Security Telemetry</h4>
      <div class="cyber-log-table">
        <div class="cyber-log-header">
          <span>Time</span>
          <span>Event</span>
          <span>Source</span>
        </div>
        ${telemetryRows}
      </div>
    </div>

    <div class="cyber-section">
      <div class="cyber-ai-header">
        <h4 class="cyber-section-title">🤖 AI Analysis</h4>
        <button class="btn btn-cyber btn-sm" id="cyber-analyze-btn" onclick="cyberTimelineAnalyze(${index})">
          ▶ Run AI Analysis
        </button>
      </div>
      <div class="cyber-ai-output" id="cyber-ai-output">
        <div class="cyber-ai-placeholder">Click "Run AI Analysis" to process this phase's telemetry with the LLM.</div>
      </div>
    </div>
  `;

  // Scroll to detail
  detail.scrollTop = 0;
}

async function cyberTimelineAnalyze(index) {
  const phase = CYBER_TIMELINE_PHASES[index];
  if (!phase) return;

  const btn = document.getElementById('cyber-analyze-btn');
  const output = document.getElementById('cyber-ai-output');

  btn.disabled = true;
  btn.textContent = '⏳ Analyzing...';
  output.innerHTML = '<span class="typing-cursor"></span> <span style="color:var(--text-dim)">AI analyst processing telemetry...</span>';

  // Format telemetry as context
  const telemetryContext = phase.telemetry.map(t =>
    `[${t.time}] [${t.severity.toUpperCase()}] [${t.source}] ${t.event}`
  ).join('\n');

  const systemPrompt = `You are an elite AI security analyst working in a SOC. You are analyzing a real-world incident based on the HuggingFace July 2026 security breach. Provide technical, actionable analysis. Use markdown formatting with headers, bullet points, and code blocks where appropriate. Be concise but thorough.`;

  const userMessage = `## Phase: ${phase.title}
## MITRE: ${phase.mitre}
## Timestamp: ${phase.timestamp}

## Security Telemetry
${telemetryContext}

## Your Task
${phase.aiPrompt}`;

  try {
    const fullText = await callLLM([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage }
    ], (chunk) => {
      output.innerHTML = formatMarkdown(chunk) + '<span class="typing-cursor"></span>';
    });

    output.innerHTML = formatMarkdown(fullText);
    btn.disabled = false;
    btn.textContent = '▶ Re-run Analysis';
  } catch (e) {
    output.innerHTML = `<div class="error-card"><strong>❌ Analysis failed.</strong><br><span class="dim">${e.message || 'Unknown error'}</span></div>`;
    btn.disabled = false;
    btn.textContent = '▶ Run AI Analysis';
  }
}
