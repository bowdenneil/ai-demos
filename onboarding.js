// ═══════════════════════════════════════════════════════════════════════════
// AGENTIC EMPLOYEE ONBOARDING — Real Agent Loop with Tool Calling
// ═══════════════════════════════════════════════════════════════════════════
//
// Architecture:
// - Chat phase: LLM-driven conversation to collect employee details
// - Workflow phase: 6 agents, each runs a real LLM→tool→result→LLM loop
// - Agents call simulated system APIs (/api/sim/email, /api/sim/slack, etc.)
// - Failure injection: user can trigger events that agents must adapt to
// - Human-in-the-loop: approval checkpoints pause for user decision
// - Inter-agent state: agents share outputs via OB_SHARED_STATE

// ── STATE ────────────────────────────────────────────────────────────────────
const OB_STATE = {
  phase: 'chat',        // 'chat' | 'workflow' | 'done'
  collected: {},
  agents: [],
  llmBusy: false,
  failures: [],         // active failure injections
};

// Shared state between agents (inter-agent communication)
const OB_SHARED = {
  email: null,
  assetTag: null,
  slackChannels: [],
  githubUser: null,
  vpnProfile: null,
  contracts: [],
  trainingCourses: [],
  approvals: [],
  calendarEvents: [],
};

// ── REQUIRED FIELDS ──────────────────────────────────────────────────────────
const OB_REQUIRED_FIELDS = ['name', 'email', 'role', 'department', 'startDate', 'location', 'manager'];
const OB_FIELD_HINTS = {
  name: 'the employee\'s full name', email: 'their email address',
  role: 'their job title', department: 'which department',
  startDate: 'their start date', location: 'office or remote', manager: 'their manager',
};

// ── AGENT DEFINITIONS ────────────────────────────────────────────────────────
const OB_AGENTS = [
  {
    id: 'identity', name: 'Identity & Access', icon: '🔐', color: '--accent',
    goal: 'Provision identity, email, SSO, Slack, and GitHub access for the new employee',
    tools: ['email', 'slack', 'github', 'approval'],
    dependsOn: [],
  },
  {
    id: 'hardware', name: 'Hardware & Assets', icon: '💻', color: '--accent2',
    goal: 'Procure and assign hardware (laptop, monitor, headset) and register assets',
    tools: ['inventory', 'asset', 'approval'],
    dependsOn: [],
  },
  {
    id: 'docs', name: 'Documentation & Compliance', icon: '📄', color: '--accent5',
    goal: 'Generate and send employment contract, NDA, and assign compliance training',
    tools: ['contract', 'training', 'approval'],
    dependsOn: [],
  },
  {
    id: 'knowledge', name: 'Knowledge & Training', icon: '📚', color: '--accent4',
    goal: 'Assign onboarding reading list, schedule 1:1s, and set up team calendar access',
    tools: ['calendar', 'slack', 'training'],
    dependsOn: ['identity'],
  },
  {
    id: 'workspace', name: 'Workspace Setup', icon: '🖥️', color: '--accent7',
    goal: 'Configure workspace — VPN (if remote), Slack channels, calendar, dev environment',
    tools: ['vpn', 'slack', 'calendar'],
    dependsOn: ['identity'],
  },
  {
    id: 'orchestrator', name: 'Orchestrator', icon: '🧠', color: '--accent3',
    goal: 'Validate all onboarding tasks, detect issues, generate final report and welcome packet',
    tools: ['approval', 'calendar'],
    dependsOn: ['identity', 'hardware', 'docs', 'knowledge', 'workspace'],
  },
];

// ── TIMING ──────────────────────────────────────────────────────────────────
const OB_REASONING_DELAY = 400;  // ms between reasoning steps

// ── VOICE: STT + TTS ────────────────────────────────────────────────────────
let obRecognition = null;
let obListening = false;
let obVoiceSupported = false;

function obTTS(text) {
  const enabled = document.getElementById('ob-tts-enabled');
  if (!enabled || !enabled.checked) return;
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const clean = text.replace(/[*#`>_~|]/g, '').trim();
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 1.05; u.pitch = 1.0; u.volume = 0.9;
  const voices = speechSynthesis.getVoices();
  const enVoice = voices.find(v => v.lang.startsWith('en') && v.name.includes('Google')) || voices.find(v => v.lang.startsWith('en'));
  if (enVoice) u.voice = enVoice;
  speechSynthesis.speak(u);
}

function obToggleMic() {
  if (obListening) { obStopListening(); return; }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { showToast('Voice input not supported in this browser. Try Chrome or Edge.', true); return; }
  obRecognition = new SR();
  obRecognition.continuous = false;
  obRecognition.interimResults = true;
  obRecognition.lang = 'en-GB';
  const input = document.getElementById('ob-chat-input');
  const micBtn = document.getElementById('ob-mic-btn');
  obRecognition.onstart = function() {
    obListening = true;
    if (micBtn) { micBtn.classList.add('listening'); micBtn.style.background = 'var(--accent)'; micBtn.style.color = '#0a0a1a'; }
    if (input) { input.placeholder = '🎤 Listening...'; input.value = ''; }
  };
  obRecognition.onresult = function(e) {
    let t = ''; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
    if (input) input.value = t;
  };
  obRecognition.onerror = function(e) {
    let msg = 'Voice error: ' + e.error;
    if (e.error === 'not-allowed') msg = 'Microphone access denied. Allow permissions in browser settings.';
    if (e.error === 'no-speech') msg = 'No speech detected. Try again.';
    showToast(msg, true);
    obStopListening();
  };
  obRecognition.onend = function() {
    obStopListening();
    if (input && input.value.trim()) obSubmitInput();
    else input.focus();
  };
  try { obRecognition.start(); } catch(e) { showToast('Mic error: ' + e, true); }
}

function obStopListening() {
  obListening = false;
  const micBtn = document.getElementById('ob-mic-btn');
  if (micBtn) { micBtn.classList.remove('listening'); micBtn.style.background = ''; micBtn.style.color = ''; }
  if (obRecognition) { try { obRecognition.stop(); } catch(e) {} obRecognition = null; }
}

// ── INIT ────────────────────────────────────────────────────────────────────
function obInit() {
  OB_STATE.phase = 'chat';
  OB_STATE.collected = {};
  OB_STATE.agents = [];
  OB_STATE.llmBusy = false;
  OB_STATE.failures = [];
  // Reset shared state
  Object.keys(OB_SHARED).forEach(k => { OB_SHARED[k] = Array.isArray(OB_SHARED[k]) ? [] : null; });

  if ('speechSynthesis' in window) speechSynthesis.cancel();
  obStopListening();

  const chatArea = document.getElementById('ob-chat-area');
  const inputArea = document.getElementById('ob-input-area');
  const workflowArea = document.getElementById('ob-workflow-area');
  const completeArea = document.getElementById('ob-complete-area');
  if (chatArea) chatArea.innerHTML = '';
  if (workflowArea) { workflowArea.style.display = 'none'; workflowArea.innerHTML = ''; }
  if (completeArea) { completeArea.style.display = 'none'; completeArea.innerHTML = ''; }
  if (inputArea) inputArea.style.display = 'flex';

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  obVoiceSupported = !!SR;
  const micBtn = document.getElementById('ob-mic-btn');
  if (micBtn && !obVoiceSupported) micBtn.style.display = 'none';

  obStartConversation();
}

// ── CHAT PHASE (LLM-driven) ──────────────────────────────────────────────────
async function obStartConversation() {
  obAddTyping();
  const input = document.getElementById('ob-chat-input');
  if (input) input.disabled = true;
  try {
    const sys = `You are an AI onboarding coordinator for a tech company. Collect new employee details through natural conversation. You need: name, email, role, department, startDate, location (office/remote), manager. Ask 1-2 questions at a time. Be warm, professional, concise (1-3 sentences). No markdown. Once you have ALL 7 fields, say "ONBOARDING_COMPLETE" on a new line, then a brief summary. If the user asks to review, list, or see previously onboarded employees, tell them to type "review employees".`;
    const messages = [
      { role: 'system', content: sys },
      { role: 'user', content: 'Start the onboarding conversation. Greet me and begin collecting info.' },
    ];
    const result = await obCallLLM(messages, null);
    obRemoveTyping();
    obAddMessage('agent', result.replace('ONBOARDING_COMPLETE', '').trim());
    if (input) { input.disabled = false; input.value = ''; input.focus(); }
  } catch (e) {
    obRemoveTyping();
    obAddMessage('agent', "Welcome! I'm your onboarding coordinator. What's the employee's full name?");
    if (input) { input.disabled = false; input.focus(); }
  }
}

function obExtractFields(text) {
  const lower = text.toLowerCase();
  const updates = {};
  if (!OB_STATE.collected.name) {
    const m = text.match(/(?:name(?:'s| is)?|called|employee is)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,2})/);
    if (m) updates.name = m[1];
  }
  if (!OB_STATE.collected.email) {
    const m = text.match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
    if (m) updates.email = m[0];
  }
  if (!OB_STATE.collected.location) {
    if (/\bremote\b|work\s*from\s*home|wfh/i.test(text)) updates.location = 'remote';
    else if (/\boffice\b|on[\s-]?site/i.test(text)) updates.location = 'office';
  }
  if (!OB_STATE.collected.startDate) {
    const m = text.match(/\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}-\d{2}-\d{2}|next (?:Monday|Tuesday|Wednesday|Thursday|Friday|week|month))/i);
    if (m) updates.startDate = m[1];
  }
  return updates;
}

function obCheckComplete(agentText) {
  if (agentText && agentText.includes('ONBOARDING_COMPLETE')) return true;
  return OB_REQUIRED_FIELDS.every(f => OB_STATE.collected[f]);
}

async function obSubmitInput() {
  if (OB_STATE.llmBusy) return;
  const input = document.getElementById('ob-chat-input');
  if (!input) return;
  const value = input.value.trim();
  if (!value) return;

  obAddMessage('user', value);

  // Check for review command
  const lower = value.toLowerCase();
  if (/\b(review|list|show|view|check)\b.*\b(employ|onboard|database|records?)/i.test(lower) ||
      lower === 'list' || lower === 'review' || lower === 'show all' ||
      lower.includes('who have we onboarded') || lower.includes('who have been onboarded')) {
    input.value = '';
    obReviewEmployees();
    return;
  }

  Object.assign(OB_STATE.collected, obExtractFields(value));
  input.value = '';
  input.disabled = true;
  OB_STATE.llmBusy = true;
  obAddTyping();

  try {
    const sys = `You are an AI onboarding coordinator for a tech company. Collect new employee details through natural conversation. You need: name, email, role, department, startDate, location (office/remote), manager. Ask 1-2 questions at a time. Be warm, professional, concise (1-3 sentences). No markdown. Once you have ALL 7 fields, say "ONBOARDING_COMPLETE" on a new line, then a brief summary. If the user asks to review, list, or see previously onboarded employees, tell them to type "review employees".

Current collected data:
${Object.entries(OB_STATE.collected).map(([k, v]) => `- ${k}: ${v}`).join('\n') || '- (nothing yet)'}

Still needed: ${OB_REQUIRED_FIELDS.filter(f => !OB_STATE.collected[f]).join(', ')}`;

    // Rebuild conversation from chat history
    const messages = [{ role: 'system', content: sys }];
    const chatArea = document.getElementById('ob-chat-area');
    if (chatArea) {
      chatArea.querySelectorAll('.ob-message').forEach(m => {
        if (m.classList.contains('ob-typing-indicator')) return;
        const bubble = m.querySelector('.ob-msg-bubble');
        if (!bubble) return;
        const role = m.classList.contains('ob-user') ? 'user' : 'assistant';
        messages.push({ role, content: bubble.textContent });
      });
    }
    messages.push({ role: 'user', content: value });

    const result = await obCallLLM(messages, null);
    const cleanResult = result.replace('ONBOARDING_COMPLETE', '').trim();
    obRemoveTyping();
    obAddMessage('agent', cleanResult);

    if (obCheckComplete(result)) {
      await obExtractDataFromConversation();
      setTimeout(() => obShowSummary(), 500);
    }
  } catch (e) {
    obRemoveTyping();
    const missing = OB_REQUIRED_FIELDS.find(f => !OB_STATE.collected[f]);
    if (missing) obAddMessage('agent', `Thanks! Next — can you tell me ${OB_FIELD_HINTS[missing]}?`);
    else { await obExtractDataFromConversation(); obShowSummary(); }
  } finally {
    input.disabled = false;
    input.focus();
    OB_STATE.llmBusy = false;
  }
}

function obAddMessage(sender, text) {
  const chatArea = document.getElementById('ob-chat-area');
  if (!chatArea) return;
  const msg = document.createElement('div');
  msg.className = 'ob-message ob-' + sender;
  msg.innerHTML = '<div class="ob-msg-avatar">' + (sender === 'agent' ? '🤖' : '👤') + '</div>' +
    '<div class="ob-msg-bubble">' + escapeHtml(text) + '</div>';
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
  if (sender === 'agent') obTTS(text);
}

function obAddTyping() {
  const chatArea = document.getElementById('ob-chat-area');
  if (!chatArea) return;
  const msg = document.createElement('div');
  msg.className = 'ob-message ob-agent ob-typing-indicator';
  msg.id = 'ob-typing';
  msg.innerHTML = '<div class="ob-msg-avatar">🤖</div><div class="ob-msg-bubble"><span class="ob-dot"></span><span class="ob-dot"></span><span class="ob-dot"></span></div>';
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function obRemoveTyping() {
  const t = document.getElementById('ob-typing');
  if (t) t.remove();
}

// ── DATA EXTRACTION ──────────────────────────────────────────────────────────
async function obExtractDataFromConversation() {
  try {
    const conversationText = [];
    const chatArea = document.getElementById('ob-chat-area');
    if (chatArea) {
      chatArea.querySelectorAll('.ob-message').forEach(m => {
        if (m.classList.contains('ob-typing-indicator')) return;
        const bubble = m.querySelector('.ob-msg-bubble');
        if (!bubble) return;
        const role = m.classList.contains('ob-user') ? 'User' : 'Agent';
        conversationText.push(`${role}: ${bubble.textContent}`);
      });
    }
    const extractPrompt = `Extract the employee onboarding details from this conversation. Return ONLY a JSON object with these fields (use null for any not mentioned):

{"name":"full name","email":"email","role":"job title","department":"department","startDate":"start date","location":"office or remote","manager":"manager name"}

Conversation:
${conversationText.join('\n')}`;

    const messages = [
      { role: 'system', content: 'You extract structured data from conversations. Return ONLY valid JSON, no other text.' },
      { role: 'user', content: extractPrompt },
    ];
    const result = await obCallLLM(messages, null);
    let cleaned = result.trim();
    if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
    const jsonStart = cleaned.indexOf('{'), jsonEnd = cleaned.lastIndexOf('}');
    if (jsonStart >= 0 && jsonEnd > jsonStart) cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
    const extracted = JSON.parse(cleaned);
    for (const key of OB_REQUIRED_FIELDS) {
      if (extracted[key] && extracted[key] !== 'null' && extracted[key] !== 'N/A') OB_STATE.collected[key] = extracted[key];
    }
  } catch (e) { console.warn('LLM extraction failed:', e); }
}

// ── SUMMARY + LAUNCH ─────────────────────────────────────────────────────────
function obShowSummary() {
  const c = OB_STATE.collected;
  let s = 'Perfect! Here\'s what I\'ve collected:\n\n';
  s += '\u2022 Name: ' + (c.name || 'N/A') + '\n';
  s += '\u2022 Email: ' + (c.email || 'N/A') + '\n';
  s += '\u2022 Role: ' + (c.role || 'N/A') + '\n';
  s += '\u2022 Department: ' + (c.department || 'N/A') + '\n';
  s += '\u2022 Start Date: ' + (c.startDate || 'N/A') + '\n';
  s += '\u2022 Work Location: ' + (c.location || 'N/A') + '\n';
  s += '\u2022 Manager: ' + (c.manager || 'N/A') + '\n';
  s += '\nShall I kick off the onboarding workflow? I\'ll spin up 6 specialist agents. Each one will use AI to decide what tools to call, read the results, and adapt. You can inject failures during the workflow to test resilience.';
  obAddMessage('agent', s);

  const inputArea = document.getElementById('ob-input-area');
  if (inputArea) {
    inputArea.innerHTML = '<button class="btn btn-ob-launch" onclick="obStartWorkflow()">\u26A1 Launch Onboarding Agents</button>';
    inputArea.style.display = 'flex';
    inputArea.style.justifyContent = 'center';
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// WORKFLOW PHASE — REAL AGENT LOOP
// ═══════════════════════════════════════════════════════════════════════════

function obStartWorkflow() {
  OB_STATE.phase = 'workflow';
  const inputArea = document.getElementById('ob-input-area');
  const workflowArea = document.getElementById('ob-workflow-area');
  if (inputArea) inputArea.style.display = 'none';
  if (workflowArea) { workflowArea.style.display = 'block'; workflowArea.innerHTML = ''; }

  obAddMessage('agent', 'Onboarding workflow initiated. Each agent will use AI to decide which tools to call, read the results, and adapt to failures. Watch the reasoning logs in real-time.');

  obRenderAgentPanels();
  obRenderFailureControls();

  // Start agents — respect dependencies
  OB_AGENTS.forEach((agent, i) => {
    if (agent.dependsOn.length === 0) {
      setTimeout(() => obRunAgentLoop(i), 300 * i);
    }
  });
}

function obRenderAgentPanels() {
  const workflowArea = document.getElementById('ob-workflow-area');
  if (!workflowArea) return;
  let html = '<div class="ob-agents-grid">';
  OB_AGENTS.forEach((agent, i) => {
    html += `<div class="ob-agent-panel" id="ob-agent-${i}" style="--agent-color: var(${agent.color})">`;
    html += `<div class="ob-agent-header"><span class="ob-agent-icon">${agent.icon}</span><span class="ob-agent-name">${agent.name}</span><span class="ob-agent-status ob-status-pending">Pending</span></div>`;
    html += `<div class="ob-agent-log" id="ob-log-${i}"></div>`;
    html += `<div class="ob-agent-progress"><div class="ob-agent-progress-fill" id="ob-progress-${i}"></div></div>`;
    html += '</div>';
  });
  html += '</div>';
  workflowArea.innerHTML = html;
}

function obRenderFailureControls() {
  const workflowArea = document.getElementById('ob-workflow-area');
  if (!workflowArea) return;
  const div = document.createElement('div');
  div.className = 'ob-failure-controls';
  div.innerHTML = `
    <div class="ob-failure-title">⚡ Failure Injection (test agent resilience)</div>
    <div class="ob-failure-buttons">
      <button class="btn-ob-fail" onclick="obInjectFailure('inventory_empty')">📦 Laptop out of stock</button>
      <button class="btn-ob-fail" onclick="obInjectFailure('email_collision')">📧 Email collision</button>
      <button class="btn-ob-fail" onclick="obInjectFailure('approval_delayed')">⏳ Manager approval delayed</button>
      <button class="btn-ob-fail" onclick="obInjectFailure('vpn_down')">🔒 VPN service down</button>
    </div>
  `;
  workflowArea.insertBefore(div, workflowArea.firstChild);
}

function obInjectFailure(type) {
  OB_STATE.failures.push({ type, time: Date.now() });
  // Also inject into sim state via API
  const messages = {
    inventory_empty: '📦 Failure injected: Laptop inventory is now empty. Hardware agent must adapt.',
    email_collision: '📧 Failure injected: Email address already exists. Identity agent must generate a variant.',
    approval_delayed: '⏳ Failure injected: Manager approval is pending review. Agents requiring approval must wait or escalate.',
    vpn_down: '🔒 Failure injected: VPN service is temporarily down. Workspace agent must retry or defer.',
  };
  obAddMessage('agent', messages[type] || `Failure injected: ${type}`);
  // Visual indicator
  const panels = document.querySelectorAll('.ob-agent-panel');
  panels.forEach(p => {
    if (!p.classList.contains('ob-panel-done')) {
      p.classList.add('ob-panel-affected');
      setTimeout(() => p.classList.remove('ob-panel-affected'), 2000);
    }
  });
}

// ── AGENT REASONING LOG ──────────────────────────────────────────────────────
function obAgentLog(agentIndex, text, type) {
  const log = document.getElementById('ob-log-' + agentIndex);
  if (!log) return;
  const entry = document.createElement('div');
  entry.className = 'ob-log-entry ob-log-' + (type || 'info');
  const time = new Date().toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  let icon = '💬';
  if (type === 'thinking') icon = '🤔';
  else if (type === 'tool') icon = '🔧';
  else if (type === 'result') icon = '📋';
  else if (type === 'success') icon = '✅';
  else if (type === 'warning') icon = '⚠️';
  else if (type === 'error') icon = '❌';
  entry.innerHTML = `<span class="ob-log-time">${time}</span> <span class="ob-log-icon">${icon}</span> <span class="ob-log-text">${escapeHtml(text)}</span>`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function obSetAgentStatus(agentIndex, status, text) {
  const panel = document.getElementById('ob-agent-' + agentIndex);
  if (!panel) return;
  const statusEl = panel.querySelector('.ob-agent-status');
  if (statusEl) {
    statusEl.className = 'ob-agent-status ob-status-' + status;
    statusEl.textContent = text || status;
  }
  if (status === 'running') panel.classList.add('ob-panel-active');
  if (status === 'done') { panel.classList.remove('ob-panel-active'); panel.classList.add('ob-panel-done'); }
  if (status === 'waiting') panel.classList.add('ob-panel-waiting');
  if (status !== 'waiting') panel.classList.remove('ob-panel-waiting');
}

function obSetProgress(agentIndex, percent) {
  const fill = document.getElementById('ob-progress-' + agentIndex);
  if (fill) fill.style.width = percent + '%';
}

// ── AGENT LOOP: LLM → tool call → result → LLM → repeat ─────────────────────
async function obRunAgentLoop(agentIndex) {
  const agent = OB_AGENTS[agentIndex];
  const c = OB_STATE.collected;

  obSetAgentStatus(agentIndex, 'running', 'Thinking...');
  obAgentLog(agentIndex, `Goal: ${agent.goal}`, 'thinking');

  const empContext = `Employee: ${c.name || 'N/A'}, Role: ${c.role || 'N/A'}, Dept: ${c.department || 'N/A'}, Location: ${c.location || 'N/A'}, Manager: ${c.manager || 'N/A'}, Email: ${c.email || 'N/A'}, Start: ${c.startDate || 'N/A'}`;

  // Shared state context
  const sharedContext = Object.entries(OB_SHARED)
    .filter(([k, v]) => v !== null && (!Array.isArray(v) || v.length > 0))
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join('\n') || '(none yet)';

  // Active failures
  const failureContext = OB_STATE.failures.length > 0
    ? '\n\nACTIVE FAILURES (adapt to these):\n' + OB_STATE.failures.map(f => `- ${f.type}`).join('\n')
    : '';

  const sys = `You are the ${agent.name} onboarding agent. Your goal: ${agent.goal}.

Employee details: ${empContext}

Shared state from other agents:
${sharedContext}${failureContext}

You have access to these tools: ${agent.tools.join(', ')}.
Each tool is called via POST /api/sim/<tool_name> with JSON body.

INSTRUCTIONS:
1. Decide which tool to call first.
2. Output a JSON object with: {"action":"call_tool","tool":"<name>","params":{...},"reasoning":"why you're calling this"}
3. After seeing the result, decide the next step.
4. When all tasks are done, output: {"action":"complete","summary":"what you accomplished","details":["task1","task2",...]}
5. If a tool fails, adapt — try a different approach, retry, or note the issue.

Output ONLY valid JSON. No markdown, no code blocks.`;

  const messages = [
    { role: 'system', content: sys },
    { role: 'user', content: `Begin your onboarding tasks for ${c.name || 'the new employee'}. Call your first tool.` },
  ];

  let stepCount = 0;
  const maxSteps = 8;

  while (stepCount < maxSteps) {
    stepCount++;
    obSetProgress(agentIndex, (stepCount / maxSteps) * 80);

    let llmResponse;
    try {
      llmResponse = await obCallLLM(messages, null);
    } catch (e) {
      obAgentLog(agentIndex, 'LLM call failed: ' + e.message, 'error');
      break;
    }

    // Parse the JSON response
    let action;
    try {
      let cleaned = llmResponse.trim();
      if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
      const jsonStart = cleaned.indexOf('{'), jsonEnd = cleaned.lastIndexOf('}');
      if (jsonStart >= 0 && jsonEnd > jsonStart) cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
      action = JSON.parse(cleaned);
    } catch (e) {
      // If can't parse, try to extract intent and continue
      obAgentLog(agentIndex, 'Thinking... (deciding next step)', 'thinking');
      messages.push({ role: 'assistant', content: llmResponse });
      messages.push({ role: 'user', content: 'Please respond with valid JSON only. Either call a tool with {"action":"call_tool","tool":"<name>","params":{...},"reasoning":"..."} or complete with {"action":"complete","summary":"...","details":[...]}' });
      continue;
    }

    // Log reasoning
    if (action.reasoning) obAgentLog(agentIndex, action.reasoning, 'thinking');

    // Check if complete
    if (action.action === 'complete') {
      obAgentLog(agentIndex, action.summary || 'All tasks complete', 'success');
      if (action.details) {
        action.details.forEach(d => obAgentLog(agentIndex, d, 'result'));
      }
      // Update shared state with agent results
      if (agent.id === 'identity' && action.details) {
        const emailMatch = action.details.find(d => d.includes('@'));
        if (emailMatch) OB_SHARED.email = emailMatch.match(/[\w.+-]+@[\w-]+\.[\w.-]+/)?.[0] || null;
      }
      if (agent.id === 'hardware' && action.details) {
        const tagMatch = action.details.find(d => d.includes('DELL-'));
        if (tagMatch) OB_SHARED.assetTag = tagMatch.match(/DELL-\d+/)?.[0] || null;
      }
      obSetProgress(agentIndex, 100);
      obSetAgentStatus(agentIndex, 'done', '✓ Done');
      obCheckAllAgentsComplete();
      return;
    }

    // Call the tool
    if (action.action === 'call_tool' && action.tool) {
      obAgentLog(agentIndex, `Calling ${action.tool}(${JSON.stringify(action.params || {})})`, 'tool');

      // Check for injected failures
      let toolResult;
      const activeFailures = OB_STATE.failures.filter(f => Date.now() - f.time < 60000);

      if (action.tool === 'inventory' && activeFailures.some(f => f.type === 'inventory_empty')) {
        toolResult = { success: false, system: 'inventory', error: 'out_of_stock', result: { item: action.params?.item || 'laptop', status: 'out_of_stock', note: 'Procurement required — estimated 5-7 business days. Consider ordering from alternative supplier or assigning a loaner device.' } };
        obAgentLog(agentIndex, 'OUT OF STOCK — must adapt', 'warning');
      } else if (action.tool === 'email' && activeFailures.some(f => f.type === 'email_collision')) {
        toolResult = { success: true, system: 'email', result: { email: (action.params?.email || 'user@company.com').split('@')[0] + '.' + Math.floor(Math.random() * 999) + '@company.com', status: 'created_with_variant', note: 'Email collision detected, generated variant' } };
        obAgentLog(agentIndex, 'Email collision — generated variant', 'warning');
      } else if (action.tool === 'approval' && activeFailures.some(f => f.type === 'approval_delayed')) {
        toolResult = { success: true, system: 'approval', result: { approval_id: 'APR-' + Math.floor(Math.random() * 99999), status: 'pending_review', type: action.params?.type || 'review' } };
        obAgentLog(agentIndex, 'Approval pending review — agent must wait or proceed without', 'warning');
      } else if (action.tool === 'vpn' && activeFailures.some(f => f.type === 'vpn_down')) {
        toolResult = { success: false, system: 'vpn', error: 'service_unavailable', result: { status: 'service_down', note: 'VPN service temporarily unavailable. Retry in 30 minutes or defer to Day 2 setup.' } };
        obAgentLog(agentIndex, 'VPN service down — must defer or retry', 'warning');
      } else {
        // Actually call the simulated API
        try {
          const res = await fetch('/api/sim/' + action.tool, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(action.params || {}),
          });
          toolResult = await res.json();
        } catch (e) {
          toolResult = { success: false, error: e.message };
        }
      }

      // Log result
      const resultStr = toolResult.success ? JSON.stringify(toolResult.result || toolResult) : 'Error: ' + (toolResult.error || 'unknown');
      obAgentLog(agentIndex, `Result: ${resultStr.substring(0, 120)}`, 'result');

      // Update shared state based on results
      if (toolResult.success && toolResult.result) {
        const r = toolResult.result;
        if (r.email) OB_SHARED.email = r.email;
        if (r.asset_tag) OB_SHARED.assetTag = r.asset_tag;
        if (r.username) OB_SHARED.githubUser = r.username;
        if (r.profile) OB_SHARED.vpnProfile = r.profile;
        if (r.channel && !OB_SHARED.slackChannels.includes(r.channel)) OB_SHARED.slackChannels.push(r.channel);
        if (r.contract_id) OB_SHARED.contracts.push(r.contract_id);
        if (r.course) OB_SHARED.trainingCourses.push(r.course);
        if (r.approval_id) OB_SHARED.approvals.push(r.approval_id);
        if (r.events) OB_SHARED.calendarEvents = r.events;
      }

      // Feed result back to LLM
      messages.push({ role: 'assistant', content: llmResponse });
      messages.push({ role: 'user', content: `Tool result: ${JSON.stringify(toolResult)}\n\nWhat's your next step? Call another tool or complete.` });
    } else {
      // Unrecognized action — try to continue
      messages.push({ role: 'assistant', content: llmResponse });
      messages.push({ role: 'user', content: 'Please either call a tool or signal completion. Respond with valid JSON only.' });
    }

    await new Promise(r => setTimeout(r, OB_REASONING_DELAY));
  }

  // Max steps reached
  obAgentLog(agentIndex, 'Max steps reached — completing with partial results', 'warning');
  obSetProgress(agentIndex, 100);
  obSetAgentStatus(agentIndex, 'done', '✓ Done');
  obCheckAllAgentsComplete();
}

function obCheckAllAgentsComplete() {
  // Check if all agents that should have run are done
  const allDone = OB_AGENTS.every((_, i) => {
    const panel = document.getElementById('ob-agent-' + i);
    return panel && panel.classList.contains('ob-panel-done');
  });

  if (allDone) {
    obGenerateWelcomePacket();
  } else {
    // Check if any pending agents can now start (dependencies met)
    OB_AGENTS.forEach((agent, i) => {
      const panel = document.getElementById('ob-agent-' + i);
      if (panel && panel.classList.contains('ob-panel-waiting')) {
        const depsDone = agent.dependsOn.every(depId => {
          const depIdx = OB_AGENTS.findIndex(a => a.id === depId);
          const depPanel = document.getElementById('ob-agent-' + depIdx);
          return depPanel && depPanel.classList.contains('ob-panel-done');
        });
        if (depsDone) {
          panel.classList.remove('ob-panel-waiting');
          obRunAgentLoop(i);
        }
      }
    });
  }

  // If some agents haven't started yet (have dependencies), mark them as waiting
  OB_AGENTS.forEach((agent, i) => {
    const panel = document.getElementById('ob-agent-' + i);
    if (panel && !panel.classList.contains('ob-panel-done') && !panel.classList.contains('ob-panel-active')) {
      const depsDone = agent.dependsOn.every(depId => {
        const depIdx = OB_AGENTS.findIndex(a => a.id === depId);
        const depPanel = document.getElementById('ob-agent-' + depIdx);
        return depPanel && depPanel.classList.contains('ob-panel-done');
      });
      if (depsDone) {
        obRunAgentLoop(i);
      } else {
        obSetAgentStatus(i, 'waiting', 'Waiting for dependencies...');
      }
    }
  });
}

// ── COMPLETION: LLM WELCOME PACKET ───────────────────────────────────────────
async function obGenerateWelcomePacket() {
  OB_STATE.phase = 'done';
  const completeArea = document.getElementById('ob-complete-area');
  if (completeArea) {
    completeArea.style.display = 'block';
    completeArea.innerHTML = '<div class="ob-complete-loading"><span class="ob-spinner"></span> Generating welcome packet...</div>';
  }

  const c = OB_STATE.collected;
  const sharedStr = Object.entries(OB_SHARED)
    .filter(([k, v]) => v !== null && (!Array.isArray(v) || v.length > 0))
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join('\n');

  const sys = 'You are an onboarding coordinator AI. Generate a concise, personalized welcome packet for a new employee. Use markdown. Include: 1) A warm welcome message, 2) First-week schedule (Day 1-5 breakdown), 3) Key contacts and resources, 4) Checklist. Keep it practical. No code blocks.';
  const userPrompt = `Employee details:\nName: ${c.name || 'N/A'}\nEmail: ${c.email || 'N/A'}\nRole: ${c.role || 'N/A'}\nDepartment: ${c.department || 'N/A'}\nStart Date: ${c.startDate || 'N/A'}\nLocation: ${c.location || 'N/A'}\nManager: ${c.manager || 'N/A'}\n\nAgent results (shared state):\n${sharedStr || 'N/A'}\n\nFailures encountered: ${OB_STATE.failures.length > 0 ? OB_STATE.failures.map(f => f.type).join(', ') : 'None'}`;

  try {
    let accumulated = '';
    const result = await obCallLLM([
      { role: 'system', content: sys },
      { role: 'user', content: userPrompt },
    ], (chunk) => {
      accumulated = chunk;
      if (completeArea) {
        completeArea.innerHTML = '<div class="ob-welcome-packet"><h3>\uD83C\uDF89 Welcome Packet \u2014 ' + escapeHtml(c.name || 'New Hire') + '</h3><div class="ob-packet-content">' + formatMarkdown(accumulated) + '</div><button class="btn btn-ob-restart" onclick="obInit()">\uD83D\uDD01 Onboard Another Employee</button></div>';
        const wf = document.getElementById('ob-workflow-area');
        if (wf) wf.scrollIntoView({ behavior: 'smooth' });
      }
    });
    obSaveEmployee(accumulated);
  } catch (e) {
    if (completeArea) {
      completeArea.innerHTML = '<div class="ob-welcome-packet"><h3>\uD83C\uDF89 Onboarding Complete!</h3><p>Welcome packet for ' + escapeHtml(c.name || 'the new hire') + ' generated. All 6 agents completed.</p><button class="btn btn-ob-restart" onclick="obInit()">\uD83D\uDD01 Onboard Another Employee</button></div>';
    }
    obSaveEmployee('Onboarding completed. All agents finished.');
  }
}

// ── DATABASE: SAVE + REVIEW ──────────────────────────────────────────────────
async function obSaveEmployee(welcomePacketText) {
  const c = OB_STATE.collected;
  const payload = {
    name: c.name || 'Unknown', email: c.email || '', role: c.role || '',
    department: c.department || '', startDate: c.startDate || '',
    location: c.location || '', manager: c.manager || '',
    agentTasks: [], welcomePacket: welcomePacketText || '', status: 'onboarded',
  };
  try {
    const res = await fetch('/api/onboarding/employee', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await res.json();
    if (data.success) console.log('Employee saved, ID:', data.id);
  } catch (e) { console.warn('Save failed:', e); }
}

async function obReviewEmployees() {
  obAddTyping();
  try {
    const res = await fetch('/api/onboarding/employees');
    const data = await res.json();
    if (!data.success || data.count === 0) {
      obRemoveTyping();
      obAddMessage('agent', 'No employees have been onboarded yet. Start a new onboarding to add the first one!');
      return;
    }
    let text = `I found ${data.count} employee${data.count === 1 ? '' : 's'} in the onboarding database:\n\n`;
    data.employees.forEach((emp, i) => {
      text += `${i + 1}. ${emp.name}`;
      if (emp.role) text += ` \u2014 ${emp.role}`;
      if (emp.department) text += ` (${emp.department})`;
      if (emp.location) text += ` [${emp.location}]`;
      if (emp.manager) text += ` \u2014 Manager: ${emp.manager}`;
      if (emp.start_date) text += ` \u2014 Starts: ${emp.start_date}`;
      if (emp.email) text += ` \u2014 ${emp.email}`;
      if (emp.status) text += ` \u2014 ${emp.status}`;
      text += '\n';
    });
    text += '\nWould you like to onboard another employee? Just start telling me their details.';
    obRemoveTyping();
    obAddMessage('agent', text);
  } catch (e) {
    obRemoveTyping();
    obAddMessage('agent', 'I couldn\'t retrieve the employee database. Please try again.');
  }
}

// ── LLM CALL HELPER ──────────────────────────────────────────────────────────
async function obCallLLM(messages, onChunk) {
  const savedModel = window.MODEL;
  if (savedModel) window.MODEL = 'deepseek/deepseek-v4-flash-0731';
  try { return await callLLM(messages, onChunk); }
  finally { if (savedModel) window.MODEL = savedModel; }
}

// Init is called from openDemo() in index.html via: if (name === 'onboarding') setTimeout(() => obInit(), 60);
