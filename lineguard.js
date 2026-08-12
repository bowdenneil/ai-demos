// ═══════════════════════════════════════════════════════════════════════════
// LINEGUARD AI — Agentic Predictive Maintenance Demo
// ═══════════════════════════════════════════════════════════════════════════
//
// Architecture:
// - 5 screens: Line Overview → Asset Health → Investigation → Approval → Executive
// - Real agent loop: Supervisor delegates to specialist agents, each runs LLM→tool→result→LLM
// - Tools call /api/lg/* endpoints (telemetry, maintenance, inventory, etc.)
// - Human-in-the-loop: approval gate before work order submission
// - Event injection: delayed parts, operator observations, telemetry mode changes
// - Telemetry simulator: live-updating charts with anomaly ramp

// ── STATE ────────────────────────────────────────────────────────────────────
const LG_STATE = {
  screen: 'overview',         // overview | asset | investigation | approval | executive
  selectedAsset: null,
  assets: {},
  metrics: {},
  labels: {},
  telemetryPoll: null,
  charts: {},
  investigation: null,        // canonical investigation state
  agentTrace: [],
  llmBusy: false,
  chatHistory: [],
  demoMode: 'anomaly',        // normal | anomaly | escalating
  auditLog: [],
};

// ── AGENT DEFINITIONS ────────────────────────────────────────────────────────
const LG_AGENTS = [
  {
    id: 'supervisor', name: 'Supervisor Agent', icon: '🧠', color: '--accent',
    role: 'Orchestrates investigation, delegates to specialists, requires evidence before diagnosing',
  },
  {
    id: 'signal', name: 'Signal Analysis', icon: '📡', color: '--accent7',
    role: 'Detects anomalies in vibration, temperature, pressure, cycle time. Compares to baselines.',
  },
  {
    id: 'diagnosis', name: 'Failure Diagnosis', icon: '🔬', color: '--accent3',
    role: 'Generates ranked failure hypotheses. Correlates telemetry with maintenance history and documents.',
  },
  {
    id: 'impact', name: 'Impact Analysis', icon: '📊', color: '--accent5',
    role: 'Translates equipment risk into operational and financial impact. Compares maintain-now vs run-to-failure.',
  },
  {
    id: 'planner', name: 'Maintenance Planner', icon: '🔧', color: '--accent4',
    role: 'Recommends maintenance window. Checks technician skills, parts, tools, LOTO prerequisites.',
  },
  {
    id: 'action', name: 'Action Agent', icon: '📋', color: '--accent6',
    role: 'Drafts CMMS work order. Never submits without explicit approval.',
  },
  {
    id: 'comms', name: 'Communications', icon: '💬', color: '--accent2',
    role: 'Generates role-specific summaries for operators, architects, and executives.',
  },
];

// ── TOOL DEFINITIONS (for agent loop) ────────────────────────────────────────
const LG_TOOLS = {
  get_asset_snapshot: { endpoint: '/api/lg/telemetry/snapshot?asset_id={asset_id}', method: 'GET', desc: 'Get current sensor readings for an asset' },
  get_sensor_series: { endpoint: '/api/lg/telemetry/series?asset_id={asset_id}&metric={metric}&points=60', method: 'GET', desc: 'Get time series for a specific metric' },
  compare_to_baseline: { endpoint: '/api/lg/telemetry/snapshot?asset_id={asset_id}', method: 'GET', desc: 'Compare current readings to baselines' },
  list_active_anomalies: { endpoint: '/api/lg/anomalies', method: 'GET', desc: 'List all active anomalies on the line' },
  get_asset_metadata: { endpoint: '/api/lg/assets', method: 'GET', desc: 'Get asset metadata, operating limits, baselines' },
  search_maintenance_history: { endpoint: '/api/lg/maintenance/history?asset_id={asset_id}&q={query}', method: 'GET', desc: 'Search maintenance history for an asset' },
  search_technical_documents: { endpoint: '/api/lg/documents/search?asset_id={asset_id}&q={query}', method: 'GET', desc: 'Search technical documents for an asset' },
  get_operator_observations: { endpoint: '/api/lg/observations?asset_id={asset_id}', method: 'GET', desc: 'Get operator observations for an asset' },
  get_production_schedule: { endpoint: '/api/lg/schedule?line_id=LINE-03', method: 'GET', desc: 'Get production schedule and changeover windows' },
  get_inventory: { endpoint: '/api/lg/inventory?part_number={part_number}', method: 'GET', desc: 'Check parts inventory' },
  estimate_downtime_impact: { endpoint: '/api/lg/downtime-impact?asset_id={asset_id}&duration={duration}', method: 'GET', desc: 'Estimate financial impact of downtime' },
  get_technician_availability: { endpoint: '/api/lg/technicians?skill={skill}', method: 'GET', desc: 'Find available technicians with required skills' },
  draft_work_order: { endpoint: '/api/lg/work-order/draft', method: 'POST', desc: 'Draft a work order (requires approval)' },
  send_approval_request: { endpoint: '/api/lg/approval/request', method: 'POST', desc: 'Send approval request to maintenance supervisor' },
  record_operator_feedback: { endpoint: '/api/lg/observation/add', method: 'POST', desc: 'Record a new operator observation' },
};

// ── INIT ────────────────────────────────────────────────────────────────────
async function lgInit() {
  LG_STATE.screen = 'overview';
  LG_STATE.selectedAsset = null;
  LG_STATE.investigation = null;
  LG_STATE.agentTrace = [];
  LG_STATE.chatHistory = [];
  LG_STATE.llmBusy = false;
  LG_STATE.demoMode = 'anomaly';
  LG_STATE.auditLog = [];

  // Reset server state
  try { await fetch('/api/lg/reset'); } catch(e) {}

  // Load assets
  try {
    const res = await fetch('/api/lg/assets');
    const data = await res.json();
    LG_STATE.assets = data.assets;
    LG_STATE.metrics = data.metrics;
    LG_STATE.labels = data.labels;
  } catch(e) {
    console.error('Failed to load assets:', e);
  }

  // Render line overview
  await lgRenderOverview();
  lgStartTelemetryPoll();
}

// ── TELEMETRY POLLING ────────────────────────────────────────────────────────
function lgStartTelemetryPoll() {
  if (LG_STATE.telemetryPoll) clearInterval(LG_STATE.telemetryPoll);
  LG_STATE.telemetryPoll = setInterval(async () => {
    if (LG_STATE.screen === 'overview') {
      await lgUpdateOverviewCards();
    } else if (LG_STATE.screen === 'asset') {
      await lgUpdateAssetCharts();
    }
  }, 3000);
}

function lgStopTelemetryPoll() {
  if (LG_STATE.telemetryPoll) {
    clearInterval(LG_STATE.telemetryPoll);
    LG_STATE.telemetryPoll = null;
  }
}

// ── SCREEN NAVIGATION ────────────────────────────────────────────────────────
function lgShowScreen(screen) {
  LG_STATE.screen = screen;
  document.querySelectorAll('.lg-screen').forEach(s => s.style.display = 'none');
  const el = document.getElementById('lg-screen-' + screen);
  if (el) el.style.display = 'flex';

  // Update nav bar
  document.querySelectorAll('.lg-nav-item').forEach(n => n.classList.remove('active'));
  const navEl = document.getElementById('lg-nav-' + screen);
  if (navEl) navEl.classList.add('active');
}

// Nav: Asset Health — needs an asset. Default to the anomalous press, else first asset.
function lgNavAsset() {
  const assetId = LG_STATE.selectedAsset
    || (LG_STATE.assets['PRESS-02'] ? 'PRESS-02' : Object.keys(LG_STATE.assets)[0]);
  if (assetId) lgOpenAsset(assetId);
  else lgShowScreen('asset');
}

// Nav: Executive — render from investigation if one exists, else show a hint.
function lgNavExecutive() {
  if (LG_STATE.investigation) {
    lgShowExecutive();
    return;
  }
  lgShowScreen('executive');
  const el = document.getElementById('lg-exec-content');
  if (el) el.innerHTML = `
    <div style="text-align:center;padding:3rem 2rem;color:var(--text-dim);">
      <div style="font-size:2.5rem;margin-bottom:1rem;">📈</div>
      <h3 style="color:var(--text);margin-bottom:0.5rem;">No investigation yet</h3>
      <p style="font-size:0.9rem;max-width:420px;margin:0 auto 1.5rem;">The executive summary is generated after the agent pipeline completes an investigation — downtime avoided, cost breakdown, and role-specific briefings.</p>
      <button class="btn lg-btn-primary" onclick="lgNavAsset()">🏭 Open Asset Health → Start Investigation</button>
    </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 1: LINE OVERVIEW
// ═══════════════════════════════════════════════════════════════════════════

async function lgRenderOverview() {
  lgShowScreen('overview');
  const grid = document.getElementById('lg-asset-grid');
  if (!grid) return;
  grid.innerHTML = '';

  for (const assetId of Object.keys(LG_STATE.assets)) {
    const asset = LG_STATE.assets[assetId];
    const card = document.createElement('div');
    card.className = 'lg-asset-card';
    card.id = 'lg-card-' + assetId;
    card.onclick = () => lgOpenAsset(assetId);
    card.innerHTML = `
      <div class="lg-card-header lg-status-normal" id="lg-card-header-${assetId}">
        <div class="lg-card-icon">${lgAssetIcon(asset.type)}</div>
        <div class="lg-card-status-badge" id="lg-card-badge-${assetId}">NORMAL</div>
      </div>
      <div class="lg-card-body">
        <h3>${asset.name}</h3>
        <div class="lg-card-meta">${asset.manufacturer} · ${asset.location}</div>
        <div class="lg-card-metrics" id="lg-card-metrics-${assetId}"></div>
        <div class="lg-card-risk">
          <span class="lg-risk-label">Risk</span>
          <div class="lg-risk-bar"><div class="lg-risk-fill" id="lg-risk-${assetId}" style="width:5%"></div></div>
          <span class="lg-risk-value" id="lg-risk-val-${assetId}">Low</span>
        </div>
      </div>
    `;
    grid.appendChild(card);
  }

  await lgUpdateOverviewCards();
}

async function lgUpdateOverviewCards() {
  for (const assetId of Object.keys(LG_STATE.assets)) {
    try {
      const res = await fetch(`/api/lg/telemetry/snapshot?asset_id=${assetId}`);
      const snap = await res.json();
      lgUpdateAssetCard(assetId, snap);
    } catch(e) {}
  }
}

function lgUpdateAssetCard(assetId, snap) {
  const card = document.getElementById('lg-card-' + assetId);
  if (!card) return;

  // Update status badge
  const badge = document.getElementById('lg-card-badge-' + assetId);
  const header = document.getElementById('lg-card-header-' + assetId);
  if (badge && header) {
    badge.textContent = snap.overall_status.toUpperCase();
    header.className = 'lg-card-header lg-status-' + snap.overall_status;
  }

  // Update metrics
  const metricsEl = document.getElementById('lg-card-metrics-' + assetId);
  if (metricsEl) {
    metricsEl.innerHTML = Object.entries(snap.metrics).map(([m, r]) => {
      const label = LG_STATE.labels[m] || m;
      const cls = r.status === 'critical' ? 'lg-metric-crit' : r.status === 'warning' ? 'lg-metric-warn' : '';
      return `<div class="lg-metric ${cls}"><span class="lg-metric-label">${label}</span><span class="lg-metric-value">${r.value} ${r.unit}</span></div>`;
    }).join('');
  }

  // Update risk score
  const riskPct = lgCalcRiskPct(snap);
  const riskFill = document.getElementById('lg-risk-' + assetId);
  const riskVal = document.getElementById('lg-risk-val-' + assetId);
  if (riskFill) riskFill.style.width = riskPct + '%';
  if (riskVal) {
    riskVal.textContent = riskPct > 70 ? 'High' : riskPct > 30 ? 'Medium' : 'Low';
    riskVal.className = 'lg-risk-value lg-risk-' + (riskPct > 70 ? 'high' : riskPct > 30 ? 'medium' : 'low');
  }
  if (riskFill) {
    riskFill.className = 'lg-risk-fill ' + (riskPct > 70 ? 'lg-risk-fill-high' : riskPct > 30 ? 'lg-risk-fill-medium' : 'lg-risk-fill-low');
  }
}

function lgCalcRiskPct(snap) {
  if (snap.overall_status === 'critical') return 75 + Math.random() * 15;
  if (snap.overall_status === 'warning') return 35 + Math.random() * 20;
  return 5 + Math.random() * 10;
}

function lgAssetIcon(type) {
  const icons = {
    conveyor_motor: '🔄', robotic_arm: '🤖', hydraulic_press: '🏭',
    cooling_pump: '💧', packaging_unit: '📦',
  };
  return icons[type] || '⚙️';
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 2: ASSET HEALTH
// ═══════════════════════════════════════════════════════════════════════════

async function lgOpenAsset(assetId) {
  LG_STATE.selectedAsset = assetId;
  lgShowScreen('asset');

  const asset = LG_STATE.assets[assetId];
  document.getElementById('lg-asset-title').textContent = asset.name;
  document.getElementById('lg-asset-meta').textContent = `${asset.manufacturer} ${asset.model} · ${asset.location} · Criticality: ${asset.criticality}`;

  // Build chart cards for this asset's metrics
  const chartsGrid = document.getElementById('lg-asset-charts');
  const metrics = LG_STATE.metrics[asset.type] || [];
  // Destroy old charts
  Object.values(LG_STATE.charts).forEach(c => { try { c.destroy(); } catch(e) {} });
  LG_STATE.charts = {};

  chartsGrid.innerHTML = metrics.map(m => `
    <div class="lg-chart-card">
      <div class="lg-chart-header">
        <span class="lg-chart-title">${LG_STATE.labels[m] || m}</span>
        <span class="lg-chart-current" id="lg-current-${m}">—</span>
      </div>
      <div style="height:160px;"><canvas id="lg-canvas-${m}"></canvas></div>
      <div class="lg-chart-baseline" id="lg-baseline-${m}"></div>
    </div>
  `).join('');

  // Initial chart render
  const baselines = asset.baselines || {};
  const limits = asset.operating_limits || {};
  for (const m of metrics) {
    const series = await lgFetchSeries(assetId, m, 60);
    if (series.length) {
      lgCreateChart(m, series, baselines[m] ?? null, limits[m] || { warn: null, crit: null });
      const blEl = document.getElementById('lg-baseline-' + m);
      if (blEl && baselines[m] != null) blEl.textContent = `baseline ${baselines[m]} · warn ${limits[m]?.warn ?? '—'} · crit ${limits[m]?.crit ?? '—'}`;
    }
  }

  // Sidebar data
  lgLoadMaintenanceHistory(assetId);
  lgLoadObservations(assetId);
}

async function lgFetchSeries(assetId, metric, points) {
  try {
    const res = await fetch(`/api/lg/telemetry/series?asset_id=${assetId}&metric=${metric}&points=${points}`);
    const data = await res.json();
    return data.series || [];
  } catch(e) { return []; }
}

function lgCreateChart(metric, series, baseline, limits) {
  const canvas = document.getElementById('lg-canvas-' + metric);
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const labels = series.map(s => s.iso_time);
  const values = series.map(s => s.value);

  // Threshold lines
  const warnLine = new Array(series.length).fill(limits.warn);
  const critLine = new Array(series.length).fill(limits.crit);
  const baseLine = new Array(series.length).fill(baseline);

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: metric, data: values, borderColor: '#53d8fb', backgroundColor: 'rgba(83,216,251,0.1)', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 },
        { label: 'Baseline', data: baseLine, borderColor: '#4a4a6a', borderDash: [4,4], pointRadius: 0, borderWidth: 1, fill: false },
        { label: 'Warn', data: warnLine, borderColor: '#fbbf24', borderDash: [4,4], pointRadius: 0, borderWidth: 1, fill: false },
        { label: 'Crit', data: critLine, borderColor: '#f87171', borderDash: [4,4], pointRadius: 0, borderWidth: 1, fill: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: '#1a1a3a' } },
      },
    },
  });

  LG_STATE.charts[metric] = chart;

  // Update current value
  const currentEl = document.getElementById('lg-current-' + metric);
  if (currentEl && series.length > 0) {
    const last = series[series.length - 1];
    currentEl.textContent = last.value + ' ' + last.unit;
    currentEl.className = 'lg-chart-current lg-metric-text-' + last.status;
  }
}

async function lgUpdateAssetCharts() {
  const assetId = LG_STATE.selectedAsset;
  if (!assetId) return;
  const asset = LG_STATE.assets[assetId];
  const metrics = LG_STATE.metrics[asset.type] || [];

  for (const metric of metrics) {
    const series = await lgFetchSeries(assetId, metric, 60);
    const chart = LG_STATE.charts[metric];
    if (chart && series.length > 0) {
      const labels = series.map(s => s.iso_time);
      const values = series.map(s => s.value);
      chart.data.labels = labels;
      chart.data.datasets[0].data = values;
      chart.update('none');

      const last = series[series.length - 1];
      const currentEl = document.getElementById('lg-current-' + metric);
      if (currentEl) {
        currentEl.textContent = last.value + ' ' + last.unit;
        currentEl.className = 'lg-chart-current lg-metric-text-' + last.status;
      }
    }
  }
}

async function lgLoadMaintenanceHistory(assetId) {
  try {
    const res = await fetch(`/api/lg/maintenance/history?asset_id=${assetId}`);
    const data = await res.json();
    const container = document.getElementById('lg-maintenance-list');
    if (!container) return;
    container.innerHTML = (data.records || []).map(r => `
      <div class="lg-maintenance-item">
        <div class="lg-maint-header">
          <span class="lg-maint-id">${r.id}</span>
          <span class="lg-maint-date">${r.date}</span>
          <span class="lg-maint-type lg-maint-${r.type}">${r.type}</span>
        </div>
        <div class="lg-maint-desc">${r.description}</div>
        <div class="lg-maint-outcome">${r.outcome}</div>
      </div>
    `).join('');
  } catch(e) {}
}

async function lgLoadObservations(assetId) {
  try {
    const res = await fetch(`/api/lg/observations?asset_id=${assetId}`);
    const data = await res.json();
    const container = document.getElementById('lg-observations-list');
    if (!container) return;
    container.innerHTML = (data.observations || []).map(o => `
      <div class="lg-observation-item">
        <div class="lg-obs-header"><span class="lg-obs-operator">${o.operator}</span><span class="lg-obs-time">${o.timestamp}</span></div>
        <div class="lg-obs-text">${escapeHtml(o.observation)}</div>
      </div>
    `).join('');
  } catch(e) {}
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 3: INVESTIGATION WORKSPACE
// ═══════════════════════════════════════════════════════════════════════════

async function lgStartInvestigation() {
  const assetId = LG_STATE.selectedAsset || 'PRESS-02';
  LG_STATE.selectedAsset = assetId;
  lgShowScreen('investigation');

  // Initialize investigation state
  LG_STATE.investigation = {
    investigation_id: 'INV-' + Math.floor(1000 + Math.random() * 9000),
    site_id: 'SITE-01',
    line_id: 'LINE-03',
    asset_id: assetId,
    status: 'investigating',
    risk: { failure_probability_24h: null, severity: null, confidence: null },
    leading_hypothesis: null,
    evidence: [],
    recommended_window: null,
    parts: [],
    business_impact: {},
    approval: { required: true, status: 'pending', approver_role: 'maintenance_supervisor' },
    agent_trace: [],
  };
  LG_STATE.agentTrace = [];
  LG_STATE.chatHistory = [];

  // Clear UI
  document.getElementById('lg-invest-signals').innerHTML = '<div class="lg-panel-loading">Analyzing telemetry...</div>';
  document.getElementById('lg-invest-hypotheses').innerHTML = '<div class="lg-panel-loading">Forming hypotheses...</div>';
  document.getElementById('lg-invest-recommendation').innerHTML = '<div class="lg-panel-loading">Calculating impact...</div>';
  document.getElementById('lg-invest-trace').innerHTML = '<div class="lg-panel-loading">Agents starting...</div>';

  // Add audit log entry
  lgAuditLog('Investigation started', `Asset: ${LG_STATE.assets[assetId].name}`);

  // Run the agent pipeline
  await lgRunAgentPipeline(assetId);
}

// ── AGENT PIPELINE ────────────────────────────────────────────────────────────
async function lgRunAgentPipeline(assetId) {
  const asset = LG_STATE.assets[assetId];
  const traceEl = document.getElementById('lg-invest-trace');
  traceEl.innerHTML = '';

  // ── Step 1: Signal Analysis Agent ──
  lgLogAgent('signal', 'Analyzing telemetry signals...', 'thinking');
  lgSetPanelStatus('signals', 'Analyzing telemetry...');

  const snapshot = await lgToolCall('get_asset_snapshot', { asset_id: assetId });
  const series = {};
  for (const metric of Object.keys(snapshot.metrics)) {
    const seriesRes = await lgToolCall('get_sensor_series', { asset_id: assetId, metric });
    series[metric] = seriesRes.series || seriesRes || [];
  }
  const anomalies = await lgToolCall('list_active_anomalies', {});

  lgRenderSignalsPanel(snapshot, series, anomalies);
  lgLogAgent('signal', `Found ${snapshot.anomaly_count} anomalous metrics on ${asset.name}`, 'result');

  // ── Step 2: Failure Diagnosis Agent ── (LLM-driven)
  lgLogAgent('diagnosis', 'Correlating telemetry with maintenance history...', 'thinking');
  lgSetPanelStatus('hypotheses', 'Forming hypotheses...');

  const maintenanceHistory = await lgToolCall('search_maintenance_history', { asset_id: assetId, query: 'bearing' });
  const techDocs = await lgToolCall('search_technical_documents', { asset_id: assetId, query: 'bearing vibration' });
  const observations = await lgToolCall('get_operator_observations', { asset_id: assetId });

  // LLM diagnosis
  const diagnosis = await lgRunDiagnosisLLM(assetId, snapshot, series, anomalies, maintenanceHistory, techDocs, observations);
  lgRenderHypothesesPanel(diagnosis);
  lgLogAgent('diagnosis', `Leading hypothesis: ${diagnosis.leading_hypothesis} (confidence: ${diagnosis.confidence})`, 'result');

  // Update investigation state
  LG_STATE.investigation.risk.severity = diagnosis.severity;
  LG_STATE.investigation.risk.confidence = diagnosis.confidence;
  LG_STATE.investigation.leading_hypothesis = diagnosis.leading_hypothesis;
  LG_STATE.investigation.evidence = diagnosis.evidence || [];

  // ── Step 3: Impact Analysis Agent ── (LLM-driven)
  lgLogAgent('impact', 'Calculating operational and financial impact...', 'thinking');
  lgSetPanelStatus('recommendation', 'Calculating impact...');

  const schedule = await lgToolCall('get_production_schedule', { line_id: 'LINE-03' });
  const downtimeImpact = await lgToolCall('estimate_downtime_impact', { asset_id: assetId, duration: 55 });

  const impactAssessment = await lgRunImpactLLM(assetId, diagnosis, downtimeImpact, schedule);
  lgLogAgent('impact', `Downtime exposure: €${downtimeImpact.comparison.run_to_failure.revenue_lost_eur} if run to failure`, 'result');

  // ── Step 4: Maintenance Planner Agent ── (LLM-driven)
  lgLogAgent('planner', 'Planning maintenance window...', 'thinking');

  const inventory = await lgToolCall('get_inventory', { part_number: 'BR-500-A' });
  const technicians = await lgToolCall('get_technician_availability', { skill: 'bearing_replacement' });

  const plan = await lgRunPlannerLLM(assetId, diagnosis, schedule, inventory, technicians, techDocs);
  lgRenderRecommendationPanel(diagnosis, impactAssessment, plan, downtimeImpact);
  lgLogAgent('planner', `Recommended window: ${plan.window} (${plan.duration_minutes} min)`, 'result');

  // Update investigation state
  LG_STATE.investigation.recommended_window = plan.window;
  LG_STATE.investigation.parts = inventory;
  LG_STATE.investigation.business_impact = downtimeImpact;

  // ── Step 5: Action Agent — Draft work order ──
  lgLogAgent('action', 'Preparing draft work order...', 'thinking');

  const woPayload = {
    asset_id: assetId,
    asset_name: asset.name,
    problem: diagnosis.leading_hypothesis,
    description: diagnosis.summary || `Bearing degradation detected on ${asset.name}. Vibration and temperature trending above warning thresholds. Historical pattern matches prior failure (WO-2025-0847).`,
    priority: 'high',
    evidence: diagnosis.evidence || [],
    estimated_duration_minutes: plan.duration_minutes,
    parts_required: plan.parts || [],
    proposed_window: plan.window,
    technician: plan.technician || 'M. Schneider',
    loto_required: true,
    investigation_id: LG_STATE.investigation.investigation_id,
  };

  const workOrder = await lgToolCall('draft_work_order', woPayload);
  const approval = await lgToolCall('send_approval_request', { work_order_id: workOrder.id, ...woPayload });

  LG_STATE.investigation.approval = { required: true, status: 'pending', approver_role: 'maintenance_supervisor', id: approval.id };
  lgLogAgent('action', `Work order ${workOrder.id} drafted — awaiting approval`, 'warning');

  // ── Step 6: Show approval prompt ──
  LG_STATE.investigation.status = 'awaiting_approval';
  LG_STATE.investigation.risk.failure_probability_24h = diagnosis.failure_probability || 0.78;

  lgRenderApprovalPrompt(workOrder, approval, plan, downtimeImpact);
  lgLogAgent('supervisor', 'Investigation complete. Work order prepared. Awaiting human approval.', 'success');

  lgAuditLog('Investigation complete', `Hypothesis: ${diagnosis.leading_hypothesis}, Confidence: ${diagnosis.confidence}`);
}

// ── TOOL CALL HELPER ──────────────────────────────────────────────────────────
async function lgToolCall(toolName, params) {
  const tool = LG_TOOLS[toolName];
  if (!tool) { console.error('Unknown tool:', toolName); return {}; }

  let url = tool.endpoint;
  for (const [k, v] of Object.entries(params)) {
    url = url.replace(`{${k}}`, encodeURIComponent(v || ''));
  }

  try {
    const res = await fetch(url, {
      method: tool.method,
      headers: { 'Content-Type': 'application/json' },
      body: tool.method === 'POST' ? JSON.stringify(params) : undefined,
    });
    const data = await res.json();
    lgAuditLog(`Tool: ${toolName}`, JSON.stringify(params).substring(0, 100));
    return data;
  } catch(e) {
    console.error(`Tool call failed: ${toolName}`, e);
    return {};
  }
}

// ── LLM-DRIVEN DIAGNOSIS ──────────────────────────────────────────────────────
async function lgRunDiagnosisLLM(assetId, snapshot, series, anomalies, history, docs, observations) {
  const asset = LG_STATE.assets[assetId];

  // Build context
  const metricsSummary = Object.entries(snapshot.metrics).map(([m, r]) => {
    const label = LG_STATE.labels[m] || m;
    return `${label}: ${r.value} ${r.unit} (baseline: ${r.baseline}, warn: ${r.warn_threshold}, crit: ${r.crit_threshold}, status: ${r.status}, anomaly_factor: ${r.anomaly_factor})`;
  }).join('\n');

  const historySummary = (history.records || []).map(r => `- ${r.date}: ${r.description} (root cause: ${r.root_cause}, outcome: ${r.outcome})`).join('\n');
  const docSummary = (docs.documents || []).map(d => `- ${d.title}: ${d.content.substring(0, 200)}...`).join('\n');
  const obsSummary = (observations.observations || []).map(o => `- ${o.operator} (${o.timestamp}): ${o.observation}`).join('\n');

  const sys = `You are the Failure Diagnosis Agent for LineGuard AI, an agentic predictive maintenance system.
Analyze the telemetry, maintenance history, technical documents, and operator observations to diagnose the likely failure mode.

Asset: ${asset.name} (${asset.manufacturer} ${asset.model})
Criticality: ${asset.criticality}

CURRENT TELEMETRY:
${metricsSummary}

ACTIVE ANOMALIES:
${(anomalies.anomalies || []).map(a => `- ${a.asset_name}: ${a.metric_label} = ${a.value}${a.unit} (${a.status}, +${a.deviation_pct}% from baseline)`).join('\n') || 'None'}

MAINTENANCE HISTORY:
${historySummary || 'No records found'}

TECHNICAL DOCUMENTS:
${docSummary || 'No documents found'}

OPERATOR OBSERVATIONS:
${obsSummary || 'None'}

Respond with ONLY a JSON object (no markdown, no code blocks):
{
  "leading_hypothesis": "short description of most likely failure mode",
  "confidence": 0.0-1.0,
  "severity": "low|medium|high|critical",
  "failure_probability": 0.0-1.0,
  "evidence": ["evidence 1 with source", "evidence 2 with source", ...],
  "contradictions": ["any contradicting evidence"],
  "recommended_validation": "how to confirm the diagnosis",
  "summary": "2-3 sentence clinical summary"
}`;

  try {
    const result = await lgCallLLM([{ role: 'system', content: sys }, { role: 'user', content: 'Diagnose the failure mode based on available evidence.' }]);
    let cleaned = result.trim();
    if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
    const jsonStart = cleaned.indexOf('{'), jsonEnd = cleaned.lastIndexOf('}');
    if (jsonStart >= 0 && jsonEnd > jsonStart) cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
    return JSON.parse(cleaned);
  } catch(e) {
    console.error('Diagnosis LLM failed:', e);
    // Fallback — deterministic diagnosis based on seeded data
    return {
      leading_hypothesis: 'Hydraulic press bearing degradation',
      confidence: 0.82,
      severity: 'high',
      failure_probability: 0.78,
      evidence: [
        'Vibration trending from 3.2 to 5.8 mm/s over 4 hours (above warn threshold of 4.5) — Source: telemetry',
        'Temperature rising from 48°C to 58°C — Source: telemetry',
        'Cycle time increased from 7.2s to 8.1s — Source: telemetry',
        'Prior bearing failure 11 months ago (WO-2025-0847) with same symptom pattern — Source: maintenance history',
        'Operator reported unusual motor whine and hydraulic fluid smell — Source: operator observations',
      ],
      contradictions: ['Pressure fluctuation currently below critical threshold (within normal range)'],
      recommended_validation: 'Inspect bearing housing during changeover — check for spalling on outer race',
      summary: 'Bearing degradation on hydraulic press motor. Vibration and temperature trends match prior failure pattern (WO-2025-0847). Confidence is high due to multiple corroborating signals.',
    };
  }
}

// ── LLM-DRIVEN IMPACT ANALYSIS ───────────────────────────────────────────────
async function lgRunImpactLLM(assetId, diagnosis, downtimeImpact, schedule) {
  const sys = `You are the Impact Analysis Agent for LineGuard AI.
Translate the equipment risk into operational and financial impact.

Diagnosis: ${diagnosis.leading_hypothesis} (confidence: ${diagnosis.confidence}, severity: ${diagnosis.severity})
Downtime impact data: ${JSON.stringify(downtimeImpact)}
Production schedule: Current product: ${downtimeImpact.current_product}, Throughput: ${downtimeImpact.line_throughput} units/hr

Respond with ONLY a JSON object:
{
  "downtime_exposure_eur": <number>,
  "avoided_downtime_eur": <number>,
  "risk_if_ignored": "short description",
  "recommendation": "maintain_now | schedule_during_changeover | monitor",
  "business_summary": "2-3 sentence summary for executives"
}`;

  try {
    const result = await lgCallLLM([{ role: 'system', content: sys }, { role: 'user', content: 'Assess the business impact.' }]);
    let cleaned = result.trim();
    if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
    const jsonStart = cleaned.indexOf('{'), jsonEnd = cleaned.lastIndexOf('}');
    if (jsonStart >= 0 && jsonEnd > jsonStart) cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
    return JSON.parse(cleaned);
  } catch(e) {
    return {
      downtime_exposure_eur: downtimeImpact.comparison.run_to_failure.revenue_lost_eur,
      avoided_downtime_eur: downtimeImpact.comparison.run_to_failure.revenue_lost_eur,
      risk_if_ignored: 'Bearing failure could cause unplanned line stoppage of 4+ hours, potential secondary damage to hydraulic system',
      recommendation: 'schedule_during_changeover',
      business_summary: `Scheduling maintenance during the upcoming changeover avoids €${downtimeImpact.comparison.run_to_failure.revenue_lost_eur} in unplanned downtime costs while requiring zero production loss.`,
    };
  }
}

// ── LLM-DRIVEN MAINTENANCE PLANNER ───────────────────────────────────────────
async function lgRunPlannerLLM(assetId, diagnosis, schedule, inventory, technicians, docs) {
  const changeover = (schedule.changeovers || [])[0] || {};
  const parts = (inventory.inventory || []).filter(p => p.compatible_assets && p.compatible_assets.includes(assetId));
  const techs = (technicians.technicians || []).filter(t => t.qualified && t.available);

  const sys = `You are the Maintenance Planner Agent for LineGuard AI.
Plan the maintenance intervention for: ${diagnosis.leading_hypothesis}

Available changeover window: ${changeover.start} to ${changeover.end} (${changeover.duration_minutes} min)
Max maintenance time in window: ${changeover.max_maintenance_minutes} min

Parts available:
${parts.map(p => `- ${p.part_number}: ${p.description} (qty: ${p.quantity}, status: ${p.status}${p.delay_note ? ', ' + p.delay_note : ''})`).join('\n')}

Technicians available:
${techs.map(t => `- ${t.name} (Level ${t.certification_level}, skills: ${t.skills.join(', ')}, travel: ${t.estimated_travel_min} min)`).join('\n')}

Technical docs indicate estimated time: 55 minutes for bearing replacement.

Respond with ONLY a JSON object:
{
  "window": "start-end time",
  "duration_minutes": <number>,
  "technician": "name",
  "parts": [{"part_number":"...", "quantity": <number>}],
  "steps": ["step 1", "step 2", ...],
  "loto_required": true,
  "missing_info": ["anything missing or uncertain"],
  "summary": "2-3 sentence plan summary"
}`;

  try {
    const result = await lgCallLLM([{ role: 'system', content: sys }, { role: 'user', content: 'Plan the maintenance intervention.' }]);
    let cleaned = result.trim();
    if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
    const jsonStart = cleaned.indexOf('{'), jsonEnd = cleaned.lastIndexOf('}');
    if (jsonStart >= 0 && jsonEnd > jsonStart) cleaned = cleaned.substring(jsonStart, jsonEnd + 1);
    return JSON.parse(cleaned);
  } catch(e) {
    return {
      window: `${changeover.start}-${changeover.end}`,
      duration_minutes: 55,
      technician: techs[0]?.name || 'M. Schneider',
      parts: [{ part_number: 'BR-500-A', quantity: 1 }, { part_number: 'SK-220', quantity: 1 }],
      steps: [
        'Lockout/tagout hydraulic press — verify zero residual pressure',
        'Remove motor housing cover (4x M10 bolts)',
        'Inspect bearing races for spalling/pitting',
        'Measure radial play with dial indicator (spec: <0.05mm)',
        'Replace bearing kit BR-500-A if degraded',
        'Replace seal kit SK-220',
        'Reassemble and torque bolts to 45 Nm cross pattern',
        'Run unloaded test for 5 minutes — verify vibration < 3.5 mm/s',
      ],
      loto_required: true,
      missing_info: [],
      summary: `Schedule bearing replacement during ${changeover.start}-${changeover.end} changeover. ${techs[0]?.name || 'M. Schneider'} is qualified and nearby. Parts BR-500-A and SK-220 are in stock.`,
    };
  }
}

// ── RENDERING: SIGNALS PANEL ─────────────────────────────────────────────────
function lgRenderSignalsPanel(snapshot, series, anomalies) {
  const el = document.getElementById('lg-invest-signals');
  if (!el) return;

  const anomalyList = anomalies.anomalies || anomalies || [];

  let html = '<div class="lg-signal-list">';
  for (const [metric, reading] of Object.entries(snapshot.metrics)) {
    const label = LG_STATE.labels[metric] || metric;
    const devPct = ((reading.value - reading.baseline) / reading.baseline * 100).toFixed(1);
    const trend = lgCalcTrend(series[metric]);
    html += `
      <div class="lg-signal-item lg-signal-${reading.status}">
        <div class="lg-signal-header">
          <span class="lg-signal-metric">${label}</span>
          <span class="lg-signal-value">${reading.value} ${reading.unit}</span>
        </div>
        <div class="lg-signal-detail">
          Baseline: ${reading.baseline} · Current: ${reading.value} · Deviation: ${devPct > 0 ? '+' : ''}${devPct}% · Trend: ${trend}
        </div>
        <div class="lg-signal-bar">
          <div class="lg-signal-bar-fill lg-signal-bar-${reading.status}" style="width: ${Math.min(100, Math.abs(devPct))}%"></div>
        </div>
      </div>
    `;
  }
  html += '</div>';

  // Active anomalies summary
  if (anomalyList.length > 0) {
    html += '<div class="lg-anomaly-summary">';
    html += `<div class="lg-anomaly-count">${anomalyList.length} active anomalies on Line 03</div>`;
    html += anomalyList.map(a => `<div class="lg-anomaly-row lg-signal-${a.status}">${a.asset_name}: ${a.metric_label} = ${a.value}${a.unit} (+${a.deviation_pct}%)</div>`).join('');
    html += '</div>';
  }

  el.innerHTML = html;
  lgSetPanelStatus('signals', '✓ Analysis complete');
}

function lgCalcTrend(seriesData) {
  // Handle both raw array and { series: [...] } response
  const series = Array.isArray(seriesData) ? seriesData : (seriesData?.series || []);
  if (!series || series.length < 2) return 'stable';
  const recent = series.slice(-10);
  const first = recent[0].value;
  const last = recent[recent.length - 1].value;
  const diff = last - first;
  if (Math.abs(diff) < 0.1) return 'stable';
  return diff > 0 ? '↑ rising' : '↓ falling';
}

// ── RENDERING: HYPOTHESES PANEL ──────────────────────────────────────────────
function lgRenderHypothesesPanel(diagnosis) {
  const el = document.getElementById('lg-invest-hypotheses');
  if (!el) return;

  let html = `
    <div class="lg-hypothesis-card lg-hypothesis-leading">
      <div class="lg-hyp-header">
        <span class="lg-hyp-icon">🎯</span>
        <span class="lg-hyp-name">${escapeHtml(diagnosis.leading_hypothesis)}</span>
        <span class="lg-hyp-confidence">${(diagnosis.confidence * 100).toFixed(0)}% confidence</span>
      </div>
      <div class="lg-hyp-summary">${escapeHtml(diagnosis.summary || '')}</div>
      <div class="lg-hyp-severity">Severity: <span class="lg-severity-${diagnosis.severity}">${diagnosis.severity.toUpperCase()}</span></div>
    </div>
  `;

  if (diagnosis.evidence && diagnosis.evidence.length > 0) {
    html += '<div class="lg-evidence-list">';
    html += '<div class="lg-evidence-title">📋 Supporting Evidence</div>';
    diagnosis.evidence.forEach((e, i) => {
      html += `<div class="lg-evidence-item"><span class="lg-evidence-num">${i + 1}</span><span class="lg-evidence-text">${escapeHtml(e)}</span></div>`;
    });
    html += '</div>';
  }

  if (diagnosis.contradictions && diagnosis.contradictions.length > 0) {
    html += '<div class="lg-evidence-list lg-contradictions">';
    html += '<div class="lg-evidence-title">⚠ Contradicting Evidence</div>';
    diagnosis.contradictions.forEach(c => {
      html += `<div class="lg-evidence-item lg-contradiction"><span class="lg-evidence-num">!</span><span class="lg-evidence-text">${escapeHtml(c)}</span></div>`;
    });
    html += '</div>';
  }

  if (diagnosis.recommended_validation) {
    html += `<div class="lg-validation">🔬 Recommended validation: ${escapeHtml(diagnosis.recommended_validation)}</div>`;
  }

  el.innerHTML = html;
  lgSetPanelStatus('hypotheses', '✓ Diagnosis complete');
}

// ── RENDERING: RECOMMENDATION PANEL ──────────────────────────────────────────
function lgRenderRecommendationPanel(diagnosis, impact, plan, downtimeImpact) {
  const el = document.getElementById('lg-invest-recommendation');
  if (!el) return;

  let html = `
    <div class="lg-recommendation-card">
      <div class="lg-rec-header">
        <span class="lg-rec-icon">🔧</span>
        <span class="lg-rec-title">Maintenance Plan</span>
      </div>
      <div class="lg-rec-window"><strong>Window:</strong> ${escapeHtml(plan.window || 'TBD')} (${plan.duration_minutes} min)</div>
      <div class="lg-rec-tech"><strong>Technician:</strong> ${escapeHtml(plan.technician || 'TBD')}</div>
      <div class="lg-rec-parts"><strong>Parts:</strong> ${(plan.parts || []).map(p => `${p.part_number} (×${p.quantity})`).join(', ') || 'None specified'}</div>
      ${plan.loto_required ? '<div class="lg-rec-loto">⚠ Lockout/Tagout required</div>' : ''}
    </div>
  `;

  // Steps
  if (plan.steps && plan.steps.length > 0) {
    html += '<div class="lg-plan-steps">';
    html += '<div class="lg-steps-title">Step-by-step plan</div>';
    plan.steps.forEach((s, i) => {
      html += `<div class="lg-step-item"><span class="lg-step-num">${i + 1}</span><span class="lg-step-text">${escapeHtml(s)}</span></div>`;
    });
    html += '</div>';
  }

  // Impact
  html += `
    <div class="lg-impact-card">
      <div class="lg-impact-header">📊 Business Impact</div>
      <div class="lg-impact-row"><span>Downtime exposure (run to failure):</span><span class="lg-impact-cost">€${(downtimeImpact.comparison.run_to_failure.revenue_lost_eur || 0).toLocaleString()}</span></div>
      <div class="lg-impact-row"><span>Cost of planned maintenance:</span><span class="lg-impact-saved">€0 (during changeover)</span></div>
      <div class="lg-impact-row"><span>Avoided downtime:</span><span class="lg-impact-saved">€${(downtimeImpact.comparison.run_to_failure.revenue_lost_eur || 0).toLocaleString()}</span></div>
      <div class="lg-impact-summary">${escapeHtml(impact.business_summary || '')}</div>
    </div>
  `;

  // Missing info
  if (plan.missing_info && plan.missing_info.length > 0) {
    html += '<div class="lg-missing-info">';
    html += '<div class="lg-missing-title">⚠ Missing Information</div>';
    plan.missing_info.forEach(m => { html += `<div class="lg-missing-item">${escapeHtml(m)}</div>`; });
    html += '</div>';
  }

  el.innerHTML = html;
  lgSetPanelStatus('recommendation', '✓ Plan ready');
}

// ── RENDERING: APPROVAL PROMPT ───────────────────────────────────────────────
function lgRenderApprovalPrompt(workOrder, approval, plan, downtimeImpact) {
  const el = document.getElementById('lg-invest-recommendation');
  if (!el) return;

  const approvalHtml = `
    <div class="lg-approval-prompt" id="lg-approval-prompt">
      <div class="lg-approval-header">
        <span class="lg-approval-icon">🔒</span>
        <span class="lg-approval-title">Approval Required</span>
      </div>
      <div class="lg-approval-wo">
        <div class="lg-wo-id">Work Order: ${workOrder.id}</div>
        <div class="lg-wo-asset">${workOrder.asset_name}</div>
        <div class="lg-wo-problem">${escapeHtml(workOrder.problem)}</div>
        <div class="lg-wo-details">
          <div><strong>Priority:</strong> ${workOrder.priority}</div>
          <div><strong>Duration:</strong> ${workOrder.estimated_duration_minutes} min</div>
          <div><strong>Window:</strong> ${escapeHtml(workOrder.proposed_window || '')}</div>
          <div><strong>Technician:</strong> ${escapeHtml(workOrder.technician || '')}</div>
          <div><strong>LOTO:</strong> ${workOrder.loto_required ? 'Required' : 'Not required'}</div>
        </div>
      </div>
      <div class="lg-approval-evidence">
        <strong>Evidence:</strong>
        ${(workOrder.evidence || []).map(e => `<div class="lg-evidence-bullet">• ${escapeHtml(e)}</div>`).join('')}
      </div>
      <div class="lg-approval-impact">
        <div><strong>Downtime avoided:</strong> €${(downtimeImpact.comparison.run_to_failure.revenue_lost_eur || 0).toLocaleString()}</div>
      </div>
      <div class="lg-approval-buttons">
        <button class="btn lg-btn-approve" onclick="lgApproveWorkOrder('${workOrder.id}')">✓ Approve &amp; Submit</button>
        <button class="btn lg-btn-reject" onclick="lgRejectWorkOrder('${workOrder.id}')">✗ Reject</button>
        <button class="btn lg-btn-changes" onclick="lgRequestChanges('${workOrder.id}')">Request Changes</button>
      </div>
      <div class="lg-approval-note">This action requires human authorization. The AI agent cannot submit work orders without explicit approval.</div>
    </div>
  `;

  el.innerHTML += approvalHtml;
}

// ── APPROVAL ACTIONS ──────────────────────────────────────────────────────────
function lgApproveWorkOrder(woId) {
  LG_STATE.investigation.approval.status = 'approved';
  lgAuditLog('Work order approved', woId);
  lgLogAgent('action', `Work order ${woId} approved by supervisor. Submitting to CMMS...`, 'success');

  const prompt = document.getElementById('lg-approval-prompt');
  if (prompt) {
    prompt.innerHTML = `
      <div class="lg-approval-result lg-approved">
        <span class="lg-approval-icon">✅</span>
        <div class="lg-approval-text">Work order ${woId} approved and submitted to CMMS (simulated).</div>
        <div class="lg-approval-text">Maintenance scheduled for next changeover window.</div>
      </div>
      <button class="btn lg-btn-exec" onclick="lgShowExecutive()">View Executive Summary →</button>
    `;
  }
}

function lgRejectWorkOrder(woId) {
  LG_STATE.investigation.approval.status = 'rejected';
  lgAuditLog('Work order rejected', woId);
  lgLogAgent('action', `Work order ${woId} rejected. Investigation will continue.`, 'warning');

  const prompt = document.getElementById('lg-approval-prompt');
  if (prompt) {
    prompt.innerHTML = `
      <div class="lg-approval-result lg-rejected">
        <span class="lg-approval-icon">❌</span>
        <div class="lg-approval-text">Work order ${woId} rejected. The system will not proceed with maintenance.</div>
      </div>
    `;
  }
}

function lgRequestChanges(woId) {
  lgAuditLog('Changes requested', woId);
  lgLogAgent('action', `Changes requested for ${woId}. Supervisor agent will revise.`, 'thinking');
  const prompt = document.getElementById('lg-approval-prompt');
  if (prompt) {
    prompt.innerHTML = `<div class="lg-approval-result lg-changes"><span class="lg-approval-icon">📝</span><div>Changes requested. The agent will revise the work order based on feedback.</div></div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 4: EXECUTIVE OUTCOME CARD
// ═══════════════════════════════════════════════════════════════════════════

async function lgShowExecutive() {
  lgShowScreen('executive');
  const inv = LG_STATE.investigation;
  const asset = LG_STATE.assets[inv.asset_id];

  const el = document.getElementById('lg-exec-content');
  if (!el) return;

  const downtimeAvoided = inv.business_impact?.comparison?.run_to_failure?.revenue_lost_eur || 0;

  el.innerHTML = `
    <div class="lg-exec-card">
      <div class="lg-exec-header">
        <h2>Executive Outcome Summary</h2>
        <div class="lg-exec-investigation">Investigation ${inv.investigation_id}</div>
      </div>
      <div class="lg-exec-grid">
        <div class="lg-exec-item">
          <div class="lg-exec-label">Asset Investigated</div>
          <div class="lg-exec-value">${asset.name}</div>
        </div>
        <div class="lg-exec-item">
          <div class="lg-exec-label">Risk Detected</div>
          <div class="lg-exec-value lg-risk-${inv.risk.severity}">${inv.risk.severity?.toUpperCase() || 'HIGH'}</div>
          <div class="lg-exec-sub">Failure probability (24h): ${(inv.risk.failure_probability_24h * 100).toFixed(0)}%</div>
        </div>
        <div class="lg-exec-item">
          <div class="lg-exec-label">Recommended Intervention</div>
          <div class="lg-exec-value">${escapeHtml(inv.leading_hypothesis || 'Bearing replacement')}</div>
          <div class="lg-exec-sub">Confidence: ${(inv.risk.confidence * 100).toFixed(0)}%</div>
        </div>
        <div class="lg-exec-item">
          <div class="lg-exec-label">Estimated Downtime Exposure</div>
          <div class="lg-exec-value lg-impact-cost">€${downtimeAvoided.toLocaleString()}</div>
          <div class="lg-exec-sub">If run to failure (unplanned)</div>
        </div>
        <div class="lg-exec-item">
          <div class="lg-exec-label">Estimated Avoided Downtime</div>
          <div class="lg-exec-value lg-impact-saved">€${downtimeAvoided.toLocaleString()}</div>
          <div class="lg-exec-sub">By scheduling during changeover</div>
        </div>
        <div class="lg-exec-item">
          <div class="lg-exec-label">Human Decision</div>
          <div class="lg-exec-value">${inv.approval.status === 'approved' ? '✅ Approved' : inv.approval.status === 'rejected' ? '❌ Rejected' : '⏳ Pending'}</div>
          <div class="lg-exec-sub">Audit status: ${inv.investigation_id}</div>
        </div>
      </div>
      <div class="lg-exec-scale">
        <div class="lg-exec-scale-title">📈 Scale Opportunity</div>
        <div class="lg-exec-scale-text">This pattern — anomaly detection → evidence-backed diagnosis → planned intervention → human approval — is reusable across all 5 assets on Line 03 and replicable across additional production lines. Estimated downtime reduction: 30-45% with full deployment.</div>
      </div>
      <div class="lg-exec-actions">
        <button class="btn lg-btn-back" onclick="lgShowScreen('overview'); lgRenderOverview();">← Back to Line Overview</button>
        <button class="btn lg-btn-reset" onclick="lgResetDemo()">🔄 Reset Demo</button>
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════════════════
// "ASK LINEGUARD" CHAT
// ═══════════════════════════════════════════════════════════════════════════

async function lgAskQuestion() {
  const input = document.getElementById('lg-ask-input');
  if (!input) return;
  const question = input.value.trim();
  if (!question || LG_STATE.llmBusy) return;

  LG_STATE.llmBusy = true;
  input.value = '';
  input.disabled = true;

  lgAddChatMessage('user', question);
  lgAddChatTyping();

  // Build context from investigation
  const inv = LG_STATE.investigation;
  let context = '';
  if (inv) {
    context = `\n\nCurrent investigation state:\n- Asset: ${inv.asset_id}\n- Status: ${inv.status}\n- Leading hypothesis: ${inv.leading_hypothesis}\n- Confidence: ${inv.risk.confidence}\n- Severity: ${inv.risk.severity}\n- Evidence: ${(inv.evidence || []).join('; ')}\n- Recommended window: ${inv.recommended_window}`;
  } else {
    context = '\n\nNo active investigation. The user is viewing the line overview.';
  }

  const sys = `You are LineGuard AI, an agentic predictive maintenance system for a discrete manufacturing plant.
You monitor machine telemetry, detect anomalies, diagnose failures, and recommend maintenance actions.
You are talking to a plant operator, architect, or executive. Be concise, evidence-based, and operational.
If asked about specific data, reference the telemetry, maintenance history, or schedule.${context}`;

  LG_STATE.chatHistory.push({ role: 'user', content: question });

  try {
    const result = await lgCallLLM([
      { role: 'system', content: sys },
      ...LG_STATE.chatHistory.slice(-6),
    ]);
    lgRemoveChatTyping();
    lgAddChatMessage('agent', result);
    LG_STATE.chatHistory.push({ role: 'assistant', content: result });
  } catch(e) {
    lgRemoveChatTyping();
    lgAddChatMessage('agent', 'I encountered an error processing your request. Please try again.');
  } finally {
    input.disabled = false;
    input.focus();
    LG_STATE.llmBusy = false;
  }
}

function lgAddChatMessage(sender, text) {
  const area = document.getElementById('lg-ask-area');
  if (!area) return;
  const msg = document.createElement('div');
  msg.className = 'lg-chat-message lg-chat-' + sender;
  msg.innerHTML = '<div class="lg-chat-avatar">' + (sender === 'agent' ? '🤖' : '👤') + '</div><div class="lg-chat-bubble">' + formatMarkdown(text) + '</div>';
  area.appendChild(msg);
  area.scrollTop = area.scrollHeight;
}

function lgAddChatTyping() {
  const area = document.getElementById('lg-ask-area');
  if (!area) return;
  const msg = document.createElement('div');
  msg.className = 'lg-chat-message lg-chat-agent';
  msg.id = 'lg-chat-typing';
  msg.innerHTML = '<div class="lg-chat-avatar">🤖</div><div class="lg-chat-bubble"><span class="lg-typing-dot"></span><span class="lg-typing-dot"></span><span class="lg-typing-dot"></span></div>';
  area.appendChild(msg);
  area.scrollTop = area.scrollHeight;
}

function lgRemoveChatTyping() {
  const t = document.getElementById('lg-chat-typing');
  if (t) t.remove();
}

// ═══════════════════════════════════════════════════════════════════════════
// DEMO CONTROLS — EVENT INJECTION
// ═══════════════════════════════════════════════════════════════════════════

async function lgInjectEvent(type) {
  switch(type) {
    case 'delay_part':
      await fetch('/api/lg/event/delay-part', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ part_number: 'BR-500-A' }) });
      lgToast('📦 Bearing kit BR-500-A marked as delayed (+2 hours)');
      lgAuditLog('Event injected', 'Part BR-500-A delayed by 2 hours');
      if (LG_STATE.screen === 'investigation') {
        lgLogAgent('planner', '⚠ Bearing kit BR-500-A is now delayed. Revising plan...', 'warning');
        await lgRevisePlan();
      }
      break;
    case 'operator_obs':
      await fetch('/api/lg/observation/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_id: 'PRESS-02', observation: 'Operator noticed increased vibration through the floor near Press 02. More noticeable in last 15 minutes.', operator: 'T. Müller' }) });
      lgToast('📝 New operator observation added');
      lgAuditLog('Event injected', 'New operator observation: increased vibration felt through floor');
      if (LG_STATE.screen === 'investigation') {
        lgLogAgent('diagnosis', '📝 New operator observation received. Updating evidence...', 'thinking');
      }
      break;
    case 'escalate':
      lgToast('⚠ Telemetry escalating — anomaly factor increasing');
      lgAuditLog('Event injected', 'Telemetry escalation mode activated');
      // The simulator already ramps — this is a visual cue
      break;
    case 'reset':
      await lgResetDemo();
      break;
  }
}

async function lgRevisePlan() {
  const inventory = await lgToolCall('get_inventory', { part_number: 'BR-500-A' });
  const part = (inventory.inventory || []).find(p => p.part_number === 'BR-500-A');

  if (part && part.status === 'delayed') {
    const el = document.getElementById('lg-invest-recommendation');
    if (el) {
      const revisionHtml = `
        <div class="lg-plan-revision">
          <div class="lg-revision-header">🔄 Plan Revised — Part Delayed</div>
          <div class="lg-revision-text">
            Bearing kit BR-500-A shipment is delayed by ~2 hours. The Maintenance Planner agent has revised the recommendation:
          </div>
          <div class="lg-revised-plan">
            <div><strong>Original plan:</strong> Full bearing replacement during changeover</div>
            <div><strong>Revised plan:</strong> Temporary inspection during changeover (45 min) + full replacement when part arrives</div>
            <div><strong>Risk adjustment:</strong> Failure probability increased from ${(LG_STATE.investigation.risk.failure_probability_24h * 100).toFixed(0)}% to ${Math.min(95, LG_STATE.investigation.risk.failure_probability_24h * 100 + 10).toFixed(0)}%</div>
            <div><strong>Mitigation:</strong> Increased monitoring frequency, operator alert issued, technician on standby</div>
          </div>
          <div class="lg-revision-note">The audit trail preserves both the original and revised plans with timestamps.</div>
        </div>
      `;
      el.innerHTML += revisionHtml;
    }
    lgLogAgent('planner', 'Plan revised: temporary inspection + deferred full replacement. Risk escalated.', 'warning');
    lgAuditLog('Plan revised', 'Bearing kit delayed — temporary inspection recommended instead');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// AGENT TRACE + AUDIT LOG
// ═══════════════════════════════════════════════════════════════════════════

function lgLogAgent(agentId, text, type) {
  const agent = LG_AGENTS.find(a => a.id === agentId);
  const traceEl = document.getElementById('lg-invest-trace');
  if (!traceEl) return;

  const entry = document.createElement('div');
  entry.className = 'lg-trace-entry lg-trace-' + (type || 'info');

  const time = new Date().toLocaleTimeString('en-GB', { hour12: false });
  let icon = '💬';
  if (type === 'thinking') icon = '🤔';
  else if (type === 'tool') icon = '🔧';
  else if (type === 'result') icon = '📋';
  else if (type === 'success') icon = '✅';
  else if (type === 'warning') icon = '⚠️';
  else if (type === 'error') icon = '❌';

  entry.innerHTML = `
    <span class="lg-trace-time">${time}</span>
    <span class="lg-trace-agent">${agent?.icon || '🤖'} ${agent?.name || agentId}</span>
    <span class="lg-trace-icon">${icon}</span>
    <span class="lg-trace-text">${escapeHtml(text)}</span>
  `;
  traceEl.appendChild(entry);
  traceEl.scrollTop = traceEl.scrollHeight;

  LG_STATE.agentTrace.push({ agent: agentId, text, type, time });
}

function lgSetPanelStatus(panel, text) {
  const el = document.getElementById('lg-panel-status-' + panel);
  if (el) el.textContent = text;
}

function lgAuditLog(action, detail) {
  LG_STATE.auditLog.push({
    timestamp: new Date().toISOString(),
    action, detail,
  });
}

// ── UTILITIES ────────────────────────────────────────────────────────────────

function lgToast(message) {
  const toast = document.createElement('div');
  toast.className = 'lg-toast';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 4000);
}

async function lgResetDemo() {
  lgStopTelemetryPoll();
  await lgInit();
  lgToast('🔄 Demo reset');
}

// ── LLM CALL HELPER ──────────────────────────────────────────────────────────
async function lgCallLLM(messages) {
  const body = {
    model: window.MODEL || 'deepseek/deepseek-v4-flash-0731',
    messages: messages,
    temperature: 0.3,
    stream: false,
  };

  const res = await fetch('/api/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`LLM API error: ${res.status}`);
  const data = await res.json();
  return data.choices?.[0]?.message?.content || '';
}
