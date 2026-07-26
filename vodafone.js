// ─── VODAFONE IRELAND AI ROI OPTIMIZER ───
/**
 * Vodafone Ireland AI ROI Optimizer
 * Financial simulation tool for AI investment allocation across six
 * operational domains of Vodafone Ireland.
 *
 * Users adjust range sliders (one per AI investment domain) and the
 * simulator computes: annual return at maturity, Year-1 net return,
 * blended ROI %, payback period, 5-year cumulative cash flow, cost
 * savings vs revenue uplift split, and per-domain breakdowns. Four
 * Chart.js charts visualise the model. A streamed LLM strategic
 * briefing grounds the allocation in real Vodafone Group / Ireland
 * context retrieved via web search.
 *
 * Depends on portal globals (do NOT redefine):
 *   callLLM, webSearch, searchContext, renderSearchResults,
 *   formatMarkdown, postProcessLLMOutput, showToast, Chart, MODEL
 * CSS theme variables are used throughout (no hard-coded colours
 * beyond the Vodafone-red gradient palette).
 */

// Chart.js global defaults (defensive — portal may already set these).
if (typeof Chart !== 'undefined') {
  Chart.defaults.color = '#8888aa';
  Chart.defaults.borderColor = '#2a2a5a';
}

// ── 1. DOMAIN MODEL ────────────────────────────────────────────────────────
// The six AI investment domains. Each is a slider. `max` is in €M.
const VF_DOMAINS = [
  { key: 'cx',     icon: '📞', name: 'Customer Service AI', max: 5, desc: 'Chatbots, voice AI, TOBi assistant, agent assist',     roi: 3.2, savingsPct: 0.70, revPct: 0.30 },
  { key: 'net',    icon: '📡', name: 'Network Automation',  max: 8, desc: 'Self-optimizing RAN, fault detection, autonomous healing', roi: 2.8, savingsPct: 0.85, revPct: 0.15 },
  { key: 'churn',  icon: '🔄', name: 'Churn Prevention',    max: 4, desc: 'Predictive churn scoring, retention campaigns, win-back', roi: 4.5, savingsPct: 0.20, revPct: 0.80 },
  { key: 'maint',  icon: '🔧', name: 'Predictive Maintenance', max: 6, desc: 'Tower/site equipment failure prediction, truck roll reduction', roi: 3.5, savingsPct: 0.90, revPct: 0.10 },
  { key: 'energy', icon: '⚡', name: 'Energy Optimization', max: 4, desc: 'Cell site power management, cooling, renewable scheduling', roi: 2.2, savingsPct: 0.95, revPct: 0.05 },
  { key: 'rev',    icon: '📊', name: 'Revenue Intelligence', max: 5, desc: 'Dynamic pricing, ARPU uplift, personalized offers, 5G upsell', roi: 3.8, savingsPct: 0.15, revPct: 0.85 }
];

// Vodafone-red gradient palette (one colour per domain, in declaration order).
const VF_COLORS = ['#e60000', '#ff3333', '#ff6666', '#cc0000', '#ff1a1a', '#b30000'];

// Preset allocation profiles (€M per domain, keyed by domain key).
const VF_PRESETS = {
  balanced:   { cx: 2,   net: 4,   churn: 2,   maint: 3,   energy: 2,   rev: 2.5 },
  aggressive: { cx: 4,   net: 7,   churn: 3.5, maint: 5,   energy: 3.5, rev: 4   },
  lean:       { cx: 1,   net: 1.5, churn: 0.8, maint: 1,   energy: 0.5, rev: 1   },
  customer:   { cx: 4,   net: 2,   churn: 3.5, maint: 1.5, energy: 1,   rev: 3   }
};

// Vodafone Ireland context (used verbatim in the LLM briefing prompt).
const VF_CONTEXT = {
  revenue: '~€700M/year (estimate based on market share)',
  subscribers: '~2.3 million mobile subscribers',
  group: 'Part of Vodafone Group (€37B revenue); Ireland is a mid-market opco',
  aiCommitment: 'Vodafone Group has publicly committed to AI/automation across operations',
  tobi: 'TOBi chatbot handles ~70% of customer queries digitally',
  partners: 'Partnered with Google Cloud, Microsoft Azure for AI',
  tmForum: 'TM Forum autonomous networks framework participant'
};

// Ramp curve: learning → maturity. Year 3+ reaches full return.
const VF_RAMP = { 1: 0.65, 2: 0.85, 3: 1.0, 4: 1.0, 5: 1.0 };

// Runtime state.
let vfCharts = {};          // chart instances keyed by name
let vfState = {};           // last calc result (for vfAnalyze)
let vfInitialized = false;  // guard against double-init

// ── 2. INIT ────────────────────────────────────────────────────────────────
function vfInit() {
  if (vfInitialized) { vfUpdateUI(); return; }
  vfInitialized = true;
  vfBuildSliders();
  // Seed with the balanced preset so the dashboard looks alive on first open.
  vfPreset('balanced', /*silent*/ true);
}

// ── 3. SLIDERS ─────────────────────────────────────────────────────────────
function vfBuildSliders() {
  const container = document.getElementById('vf-sliders');
  if (!container) return;
  container.innerHTML = VF_DOMAINS.map((d, i) => {
    const initial = (VF_PRESETS.balanced[d.key] ?? (d.max / 2)).toFixed(1);
    return `
      <div class="vf-slider-group">
        <div class="vf-slider-label">
          <span>${d.icon} ${d.name}</span>
          <span class="vf-amount" id="vf-amount-${d.key}">€${initial}M</span>
        </div>
        <input type="range" class="vf-slider" id="vf-slider-${d.key}"
               min="0" max="${d.max}" step="0.1" value="${initial}"
               oninput="vfOnSlider('${d.key}', this.value)"
               style="accent-color: ${VF_COLORS[i]}">
        <div class="vf-slider-meta">${d.desc} · max €${d.max}M</div>
      </div>`;
  }).join('');
}

// Per-slider live handler: update the amount label then recalc.
function vfOnSlider(key, val) {
  const amt = document.getElementById('vf-amount-' + key);
  if (amt) amt.textContent = '€' + parseFloat(val).toFixed(1) + 'M';
  vfUpdateUI();
}

// Read all slider values into a {key: value} map.
function vfReadSliders() {
  const vals = {};
  VF_DOMAINS.forEach(d => {
    const el = document.getElementById('vf-slider-' + d.key);
    vals[d.key] = el ? parseFloat(el.value) : 0;
  });
  return vals;
}

// ── 4. CORE FINANCIAL MODEL ────────────────────────────────────────────────
function vfCalc() {
  const investments = vfReadSliders();
  const domains = [];
  let totalInvest = 0;
  let totalReturnY1 = 0;      // year-1 returns (after ramp)
  let totalReturnMaturity = 0; // year-3+ returns at full maturity
  let totalCostSavings = 0;
  let totalRevenueUplift = 0;

  VF_DOMAINS.forEach((d, i) => {
    const investment = investments[d.key] || 0;
    totalInvest += investment;

    // Diminishing returns above 60% of max spend.
    let dimMult = 1;
    if (investment > 0.6 * d.max) {
      dimMult = 1 - 0.3 * ((investment / d.max) - 0.6) / 0.4;
    }
    const baseReturn = investment * d.roi * dimMult; // annual return at maturity, post-diminishing-returns

    const annualReturnMaturity = baseReturn * VF_RAMP[3];
    const annualReturnY1 = baseReturn * VF_RAMP[1];
    const annualReturnY2 = baseReturn * VF_RAMP[2];

    totalReturnY1 += annualReturnY1;
    totalReturnMaturity += annualReturnMaturity;

    const costSavings = annualReturnMaturity * d.savingsPct;
    const revenueUplift = annualReturnMaturity * d.revPct;
    totalCostSavings += costSavings;
    totalRevenueUplift += revenueUplift;

    const roiPct = investment > 0 ? (annualReturnMaturity / investment) * 100 : 0;

    // 5-year cash flow: recurring annual investment, ramping returns.
    const yearly = [];
    for (let y = 1; y <= 5; y++) {
      const ret = baseReturn * (VF_RAMP[y] ?? 1.0);
      yearly.push(ret - investment); // net cash flow for that year
    }

    // Payback (months): cumulative monthly net return must exceed investment.
    // Monthly return uses maturity-level annual return (steady state).
    const monthlyReturn = annualReturnMaturity / 12;
    let paybackMonths = Infinity;
    if (monthlyReturn > 0) {
      paybackMonths = investment / monthlyReturn;
    }

    domains.push({
      ...d,
      index: i,
      color: VF_COLORS[i],
      investment,
      baseReturn,
      dimMult,
      annualReturnMaturity,
      annualReturnY1,
      annualReturnY2,
      costSavings,
      revenueUplift,
      roiPct,
      yearly,
      paybackMonths
    });
  });

  // Aggregates.
  const netReturnY1 = totalReturnY1 - totalInvest;
  const blendedRoi = totalInvest > 0 ? (totalReturnMaturity / totalInvest) * 100 : 0;

  // Blended payback: weighted by investment across domains that have a finite payback.
  let blendedPayback = Infinity;
  if (totalInvest > 0 && totalReturnMaturity > 0) {
    blendedPayback = totalInvest / (totalReturnMaturity / 12); // months
  }

  // 5-year cumulative cash flow (€M). Year 0 = -investment (capex-style outflow
  // is already folded into year-1 net; we plot cumulative from year 1).
  let cumulative = 0;
  const cumulativeCashflow = [0];
  for (let y = 1; y <= 5; y++) {
    let yearNet = 0;
    domains.forEach(dm => { yearNet += dm.yearly[y - 1]; });
    cumulative += yearNet;
    cumulativeCashflow.push(cumulative);
  }

  // Break-even year (first year cumulative >= 0, starting from year 1).
  let breakEvenYear = null;
  for (let y = 1; y <= 5; y++) {
    if (cumulativeCashflow[y] >= 0) { breakEvenYear = y; break; }
  }

  return {
    investments,
    domains,
    totalInvest,
    totalReturnY1,
    totalReturnMaturity,
    netReturnY1,
    blendedRoi,
    blendedPayback,
    totalCostSavings,
    totalRevenueUplift,
    cumulativeCashflow,
    breakEvenYear
  };
}

// ── 5. UI UPDATE ───────────────────────────────────────────────────────────
function vfUpdateUI() {
  const r = vfCalc();
  vfState = r; // cache for vfAnalyze

  // Total investment display
  const ti = document.getElementById('vf-total-invest');
  if (ti) ti.textContent = '€' + r.totalInvest.toFixed(1) + 'M';

  vfRenderMetrics(r);
  vfRenderDomainDetail(r);
  vfRenderCharts(r);
}

// ── 5a. KPI METRIC CARDS ───────────────────────────────────────────────────
function vfRenderMetrics(r) {
  const el = document.getElementById('vf-metrics');
  if (!el) return;

  const paybackTxt = isFinite(r.blendedPayback)
    ? (r.blendedPayback < 12
        ? r.blendedPayback.toFixed(1) + ' mo'
        : (r.blendedPayback / 12).toFixed(1) + ' yr')
    : '—';
  const netY1Class = r.netReturnY1 >= 0 ? 'positive' : 'negative';

  el.innerHTML = `
    <div class="vf-metric">
      <div class="vf-metric-icon">💸</div>
      <div class="vf-metric-value">€${r.totalInvest.toFixed(1)}M</div>
      <div class="vf-metric-label">Total Annual Investment</div>
      <div class="vf-metric-sub">across 6 AI domains</div>
    </div>
    <div class="vf-metric">
      <div class="vf-metric-icon">📈</div>
      <div class="vf-metric-value ${netY1Class}">€${r.netReturnY1.toFixed(1)}M</div>
      <div class="vf-metric-label">Year 1 Net Return</div>
      <div class="vf-metric-sub">returns − investment (yr 1)</div>
    </div>
    <div class="vf-metric">
      <div class="vf-metric-icon">🎯</div>
      <div class="vf-metric-value">${r.blendedRoi.toFixed(0)}%</div>
      <div class="vf-metric-label">Blended ROI (maturity)</div>
      <div class="vf-metric-sub">annual returns at full ramp</div>
    </div>
    <div class="vf-metric">
      <div class="vf-metric-icon">⏱️</div>
      <div class="vf-metric-value">${paybackTxt}</div>
      <div class="vf-metric-label">Payback Period</div>
      <div class="vf-metric-sub">cumulative returns > invest</div>
    </div>`;
}

// ── 5b. DOMAIN DETAIL ROWS ─────────────────────────────────────────────────
function vfRenderDomainDetail(r) {
  const el = document.getElementById('vf-domain-detail');
  if (!el) return;
  el.innerHTML = r.domains.map(d => {
    const roiClass = d.roiPct >= 100 ? 'positive' : 'negative';
    const payback = isFinite(d.paybackMonths)
      ? (d.paybackMonths < 12
          ? d.paybackMonths.toFixed(1) + 'mo'
          : (d.paybackMonths / 12).toFixed(1) + 'yr')
      : '—';
    return `
      <div class="vf-domain-row">
        <span class="vf-domain-icon">${d.icon}</span>
        <span class="vf-domain-name">${d.name}</span>
        <span style="min-width:70px;text-align:right">€${d.investment.toFixed(1)}M</span>
        <span style="min-width:90px;text-align:right;color:var(--success)">€${d.annualReturnMaturity.toFixed(1)}M</span>
        <span class="vf-domain-roi ${roiClass}" style="min-width:70px;text-align:right">${d.roiPct.toFixed(0)}%</span>
        <span style="min-width:60px;text-align:right">${payback}</span>
        <span style="min-width:120px;text-align:right;font-size:0.78rem;color:var(--text-dim)">
          💚€${d.costSavings.toFixed(1)}M · 📈€${d.revenueUplift.toFixed(1)}M
        </span>
      </div>`;
  }).join('');
}

// ── 5c. CHARTS ─────────────────────────────────────────────────────────────
function vfDestroyChart(name) {
  if (vfCharts[name]) { vfCharts[name].destroy(); delete vfCharts[name]; }
}

function vfRenderCharts(r) {
  vfChartRoi(r);
  vfChartCashflow(r);
  vfChartSavings(r);
  vfChartRevenue(r);
}

// Chart 1: horizontal bar — ROI % per domain.
function vfChartRoi(r) {
  vfDestroyChart('roi');
  const ctx = document.getElementById('vf-chart-roi');
  if (!ctx) return;
  vfCharts.roi = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: r.domains.map(d => d.icon + ' ' + d.name),
      datasets: [{
        label: 'ROI %',
        data: r.domains.map(d => Math.round(d.roiPct)),
        backgroundColor: r.domains.map(d => d.color),
        borderRadius: 4
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => c.parsed.x + '% ROI' } }
      },
      scales: {
        x: { ticks: { callback: v => v + '%' } }
      }
    }
  });
}

// Chart 2: line — 5-year cumulative cash flow with break-even marker.
function vfChartCashflow(r) {
  vfDestroyChart('cashflow');
  const ctx = document.getElementById('vf-chart-cashflow');
  if (!ctx) return;
  const labels = ['Year 0', 'Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5'];
  vfCharts.cashflow = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Cumulative Net Cash Flow (€M)',
        data: r.cumulativeCashflow.map(v => +v.toFixed(2)),
        borderColor: '#e60000',
        backgroundColor: 'rgba(230,0,0,0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: '#e60000'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => '€' + c.parsed.y.toFixed(1) + 'M cumulative' } }
      },
      scales: {
        y: { ticks: { callback: v => '€' + v + 'M' } }
      }
    }
  });
}

// Chart 3: doughnut — cost savings per domain.
function vfChartSavings(r) {
  vfDestroyChart('savings');
  const ctx = document.getElementById('vf-chart-savings');
  if (!ctx) return;
  vfCharts.savings = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: r.domains.map(d => d.icon + ' ' + d.name),
      datasets: [{
        data: r.domains.map(d => +d.costSavings.toFixed(2)),
        backgroundColor: r.domains.map(d => d.color),
        borderColor: '#1a1a3a',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { boxWidth: 12, font: { size: 10 } } },
        tooltip: { callbacks: { label: c => c.label + ': €' + c.parsed.toFixed(1) + 'M' } }
      }
    }
  });
}

// Chart 4: grouped bar — Year 1 vs Year 3+ revenue uplift per domain.
function vfChartRevenue(r) {
  vfDestroyChart('revenue');
  const ctx = document.getElementById('vf-chart-revenue');
  if (!ctx) return;
  vfCharts.revenue = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: r.domains.map(d => d.icon),
      datasets: [
        {
          label: 'Year 1',
          data: r.domains.map(d => +(d.annualReturnY1 * d.revPct).toFixed(2)),
          backgroundColor: '#ff6666',
          borderRadius: 3
        },
        {
          label: 'Year 3+ (maturity)',
          data: r.domains.map(d => +(d.annualReturnMaturity * d.revPct).toFixed(2)),
          backgroundColor: '#e60000',
          borderRadius: 3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { boxWidth: 12, font: { size: 10 } } },
        tooltip: { callbacks: { label: c => c.dataset.label + ': €' + c.parsed.y.toFixed(1) + 'M' } }
      },
      scales: {
        y: { ticks: { callback: v => '€' + v + 'M' } }
      }
    }
  });
}

// ── 6. PRESETS ──────────────────────────────────────────────────────────────
function vfPreset(name, silent) {
  const preset = VF_PRESETS[name];
  if (!preset) { showToast('Unknown preset: ' + name, true); return; }
  VF_DOMAINS.forEach(d => {
    const slider = document.getElementById('vf-slider-' + d.key);
    const amt = document.getElementById('vf-amount-' + d.key);
    const val = preset[d.key] ?? 0;
    if (slider) slider.value = val;
    if (amt) amt.textContent = '€' + val.toFixed(1) + 'M';
  });
  vfUpdateUI();
  if (!silent) showToast('Loaded "' + name + '" preset');
}

// ── 7. AI STRATEGIC BRIEFING ───────────────────────────────────────────────
async function vfAnalyze() {
  const output = document.getElementById('vf-output');
  const sources = document.getElementById('vf-sources');
  const btn = document.getElementById('vf-analyze-btn');
  if (!output) return;
  if (output.style.display === 'none') output.style.display = 'block';
  if (sources) sources.innerHTML = '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Analysing…'; }

  // Loading spinner.
  output.innerHTML = '<span class="typing-cursor"></span> <span style="color:var(--text-dim)">Searching for Vodafone AI context…</span>';

  // Web searches for Vodafone-specific grounding.
  let webResults = [];
  try {
    const r1 = await webSearch('Vodafone Ireland AI automation technology investment 2025 2026');
    const r2 = await webSearch('Vodafone Group AI ROI savings results');
    webResults = r1.concat(r2.slice(0, 5));
  } catch (e) { console.warn('VF web search failed:', e); }
  if (sources) renderSearchResults(webResults, 'vf-sources');
  const webCtx = searchContext(webResults);
  const webSection = webResults.length ? `\n\n## Web Search Context (cite as [web N])\n${webCtx}` : '';

  const r = vfState || vfCalc();

  // Build a compact financial-model summary for the LLM.
  const domainLines = r.domains.map(d =>
    `- ${d.icon} ${d.name}: €${d.investment.toFixed(1)}M invest → €${d.annualReturnMaturity.toFixed(1)}M annual return at maturity (ROI ${d.roiPct.toFixed(0)}%, payback ${isFinite(d.paybackMonths) ? (d.paybackMonths < 12 ? d.paybackMonths.toFixed(0) + 'mo' : (d.paybackMonths/12).toFixed(1) + 'yr') : '—'}); cost savings €${d.costSavings.toFixed(1)}M / revenue uplift €${d.revenueUplift.toFixed(1)}M`
  ).join('\n');

  const paybackTxt = isFinite(r.blendedPayback)
    ? (r.blendedPayback < 12 ? r.blendedPayback.toFixed(1) + ' months' : (r.blendedPayback/12).toFixed(1) + ' years')
    : 'not achieved within model horizon';
  const breakEvenTxt = r.breakEvenYear ? `Year ${r.breakEvenYear}` : 'not within 5 years';

  const userContent =
`You are analysing an AI investment allocation for Vodafone Ireland, modelled on Vodafone Group's publicly reported AI/automation initiatives, Irish market scale, and telecom industry benchmarks.

## Vodafone Ireland Context
- Revenue: ${VF_CONTEXT.revenue}
- Subscribers: ${VF_CONTEXT.subscribers}
- Group: ${VF_CONTEXT.group}
- AI commitment: ${VF_CONTEXT.aiCommitment}
- TOBi chatbot: ${VF_CONTEXT.tobi}
- Cloud partners: ${VF_CONTEXT.partners}
- Framework: ${VF_CONTEXT.tmForum}

## Current Investment Allocation (financial model output)
- Total annual AI investment: €${r.totalInvest.toFixed(1)}M
- Year 1 net return: €${r.netReturnY1.toFixed(1)}M (returns − investment, year-1 ramp 65%)
- Blended ROI at maturity: ${r.blendedRoi.toFixed(0)}%
- Blended payback period: ${paybackTxt}
- 5-year cumulative cash-flow break-even: ${breakEvenTxt}
- Total annual cost savings at maturity: €${r.totalCostSavings.toFixed(1)}M
- Total annual revenue uplift at maturity: €${r.totalRevenueUplift.toFixed(1)}M

## Per-Domain Breakdown
${domainLines}

## 5-Year Cumulative Cash Flow (€M)
${r.cumulativeCashflow.map((v, i) => `Year ${i}: €${v.toFixed(1)}M`).join('\n')}

Produce a CFO/CIO-level strategic briefing with these sections:
1. **Executive Summary** — 3–4 sentence board-ready brief on this allocation
2. **Portfolio Analysis** — strengths, gaps, and concentration risk across the six domains; comment on the cost-savings vs revenue-uplift balance relative to Vodafone Ireland's ~€700M revenue base
3. **Domain-by-Domain Assessment** — for each of the six domains, assess the investment level vs expected return, diminishing-returns exposure, and strategic fit with Vodafone's reported AI initiatives (TOBi, autonomous networks, churn analytics, etc.)
4. **Risk Assessment** — execution, technology, and market risks; over/under-investment flags; dependency on cloud partners (Google Cloud, Azure)
5. **Benchmark Comparison** — compare the modelled ROI and payback to Vodafone Group's reported AI savings and peer telco benchmarks (use the web sources)
6. **Recommendations** — 3–5 concrete reallocation suggestions with expected impact, phasing over year 1 → year 3, and an indicative next-step roadmap
7. **Financial Outlook** — 5-year P&L impact summary for Vodafone Ireland (€M), contribution to group AI targets, and sensitivity to the ramp curve

Use EUR for all financial figures. Cite web sources as [web N]. Format with markdown headers, bullets, and bold highlights. Be specific and quantitative — reference the model numbers above.${webSection}`;

  const messages = [
    { role: 'system', content: `You are a telecom AI strategy consultant advising Vodafone Ireland's CFO and CIO on AI investment allocation. You have deep knowledge of Vodafone Group's AI initiatives (TOBi, autonomous networks, predictive maintenance), the Irish telecoms market, and telecom AI ROI benchmarks. Use EUR for financial figures. Cite web sources as [web N]. Format with markdown headers, bullets, and bold highlights. Model: ${MODEL}.` },
    { role: 'user', content: userContent }
  ];

  output.innerHTML = '<span class="typing-cursor"></span>';
  try {
    const result = await callLLM(messages, (text) => {
      output.innerHTML = formatMarkdown(text) + '<span class="typing-cursor"></span>';
    });
    output.innerHTML = (typeof postProcessLLMOutput === 'function')
      ? postProcessLLMOutput(formatMarkdown(result))
      : formatMarkdown(result);
  } catch (e) {
    output.innerHTML = `<span style="color:var(--danger)">Error: ${e.message}</span>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🧠 Generate Strategic Briefing'; }
  }
}

// ── 8. HOOK INTO THE PORTAL ─────────────────────────────────────────────────
// openDemo('vodafone') already calls vfInit() via the patched openDemo in
// index.html. This IIFE is a defensive fallback in case the patch is missing.
(function () {
  const _origOpenDemo = window.openDemo;
  if (typeof _origOpenDemo === 'function') {
    window.openDemo = function (name) {
      const r = _origOpenDemo.apply(this, arguments);
      if (name === 'vodafone') setTimeout(() => { if (typeof vfInit === 'function') vfInit(); }, 60);
      return r;
    };
  }
})();
// ─── END VODAFONE IRELAND AI ROI OPTIMIZER ───
