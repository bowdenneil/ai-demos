// ═══════════════════════════════════════════════════════════════════════════
// A/B COMPARISON ENGINE — Reusable module for dual-model comparison
// ═══════════════════════════════════════════════════════════════════════════
// Usage:
//   ABCompare.init('demo-finance', 'fin-output', 'finQuery', {
//     buildMessages: function() { return [systemMsg, userMsg]; },
//     onBeforeRun: async function() { return sharedContext; },  // web search etc
//     onAfterRun: function(panel, result) { },  // post-processing
//   });

const ABCompare = {
  _states: {},

  init: function(demoId, outputId, runFnName, config) {
    this._states[demoId] = { outputId, runFnName, config, mode: 'single' };
    this._injectToggle(demoId, config);
  },

  _injectToggle: function(demoId, config) {
    const overlay = document.getElementById(demoId);
    if (!overlay) return;

    // Check if already injected
    if (overlay.querySelector('.ab-toggle-bar')) return;

    // Find the demo body to insert the toggle at the top
    const demoBody = overlay.querySelector('.demo-body');
    if (!demoBody) return;

    // Build the toggle + model selectors
    const bar = document.createElement('div');
    bar.className = 'ab-toggle-bar';
    bar.innerHTML = `
      <div class="ab-mode-toggle">
        <button class="ab-mode-btn active" data-mode="single" onclick="ABCompare.setMode('${demoId}','single')">Single Model</button>
        <button class="ab-mode-btn" data-mode="compare" onclick="ABCompare.setMode('${demoId}','compare')">A/B Compare</button>
      </div>
      <div class="ab-model-selectors" style="display:none">
        <div class="ab-model-group">
          <label>Model A:</label>
          <select class="ab-model-select" id="ab-model-a-${demoId}">
            <option value="deepseek/deepseek-v4-flash-0731">DeepSeek V4 Flash</option>
            <option value="z-ai/glm-5.2">GLM-5.2</option>
            <option value="anthropic/claude-sonnet-5">Claude Sonnet 5</option>
            <option value="anthropic/claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
            <option value="qwen/qwen3-235b-a22b-2507">Qwen3 235B</option>
            <option value="deepseek/deepseek-r1-0528">DeepSeek R1</option>
          </select>
        </div>
        <div class="ab-model-group">
          <label>Model B:</label>
          <select class="ab-model-select" id="ab-model-b-${demoId}">
            <option value="z-ai/glm-5.2">GLM-5.2</option>
            <option value="deepseek/deepseek-v4-flash-0731">DeepSeek V4 Flash</option>
            <option value="anthropic/claude-sonnet-5">Claude Sonnet 5</option>
            <option value="anthropic/claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
            <option value="qwen/qwen3-235b-a22b-2507">Qwen3 235B</option>
            <option value="deepseek/deepseek-r1-0528">DeepSeek R1</option>
          </select>
        </div>
      </div>
    `;
    demoBody.insertBefore(bar, demoBody.firstChild);
  },

  setMode: function(demoId, mode) {
    const state = this._states[demoId];
    if (!state) return;
    state.mode = mode;

    const overlay = document.getElementById(demoId);
    overlay.querySelectorAll('.ab-mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    const selectors = overlay.querySelector('.ab-model-selectors');
    if (selectors) selectors.style.display = mode === 'compare' ? 'flex' : 'none';

    // Don't transform output on toggle — it gets transformed when runComparison starts.
    // Just clear it and show a hint.
    const output = document.getElementById(state.outputId);
    if (output) {
      if (mode === 'compare') {
        output.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-dim);font-size:0.9rem">A/B Compare mode — select two models above and click Run.</div>';
      } else {
        output.innerHTML = '';
      }
    }
  },

  isCompareMode: function(demoId) {
    const state = this._states[demoId];
    return state && state.mode === 'compare';
  },

  getModelA: function(demoId) {
    const sel = document.getElementById('ab-model-a-' + demoId);
    return sel ? sel.value : 'deepseek/deepseek-v4-flash-0731';
  },

  getModelB: function(demoId) {
    const sel = document.getElementById('ab-model-b-' + demoId);
    return sel ? sel.value : 'z-ai/glm-5.2';
  },

  // Run both models in parallel
  runComparison: async function(demoId, messages, onChunk) {
    const modelA = this.getModelA(demoId);
    const modelB = this.getModelB(demoId);

    // Create split-screen layout NOW (after search/extraction is done)
    const state = this._states[demoId];
    const output = document.getElementById(state.outputId);
    if (output) {
      output.classList.add('ab-compare-active');
      output.innerHTML = `
        <div class="ab-split">
          <div class="ab-panel" id="ab-panel-a-${demoId}">
            <div class="ab-panel-header"><span class="ab-panel-label">${modelA.split('/').pop()}</span><span class="ab-panel-time" id="ab-time-a-${demoId}"></span></div>
            <div class="ab-panel-content" id="ab-content-a-${demoId}"><span class="typing-cursor"></span> <span style="color:var(--text-dim)">Running...</span></div>
          </div>
          <div class="ab-panel" id="ab-panel-b-${demoId}">
            <div class="ab-panel-header"><span class="ab-panel-label">${modelB.split('/').pop()}</span><span class="ab-panel-time" id="ab-time-b-${demoId}"></span></div>
            <div class="ab-panel-content" id="ab-content-b-${demoId}"><span class="typing-cursor"></span> <span style="color:var(--text-dim)">Running...</span></div>
          </div>
        </div>
      `;
    }

    const contentA = document.getElementById('ab-content-a-' + demoId);
    const contentB = document.getElementById('ab-content-b-' + demoId);
    const timeA = document.getElementById('ab-time-a-' + demoId);
    const timeB = document.getElementById('ab-time-b-' + demoId);

    // Run a model — temporarily override MODEL so callLLM uses the right model
    const runModel = async (model, contentEl, timeEl) => {
      // Save and override MODEL
      const savedModel = MODEL;
      MODEL = model;
      let fullText = '';
      const start = Date.now();
      try {
        // Build the request body manually to avoid callLLM's MODEL dependency issues
        const res = await fetch(`${API_BASE}/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: model, messages, stream: true, max_tokens: 2048 })
        });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        fullText = '';
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ') || trimmed === 'data: [DONE]') continue;
            try {
              const j = JSON.parse(trimmed.slice(6));
              const delta = j.choices?.[0]?.delta;
              const t = delta?.content || delta?.reasoning_content || '';
              if (t) {
                fullText += t;
                if (contentEl) contentEl.innerHTML = formatMarkdown(fullText) + '<span class="typing-cursor"></span>';
              }
            } catch {}
          }
        }
      } catch (e) {
        // Try non-streaming fallback
        try {
          const res2 = await fetch(`${API_BASE}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: model, messages, stream: false, max_tokens: 2048 })
          });
          const data = await res2.json();
          fullText = data.choices?.[0]?.message?.content || '';
          if (contentEl) contentEl.innerHTML = formatMarkdown(fullText) + '<span class="typing-cursor"></span>';
        } catch (e2) {
          if (contentEl) contentEl.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(e2.message)}</span>`;
        }
      }
      MODEL = savedModel;
      const elapsed = ((Date.now() - start) / 1000).toFixed(1);
      if (timeEl) timeEl.textContent = `${elapsed}s`;
      if (contentEl) {
        // Per-model cost footer (token counts estimated at ~4 chars/token)
        let footer = '';
        if (typeof LLM_PRICES !== 'undefined' && fullText) {
          const p = LLM_PRICES[model] || { inp: 0.50, out: 1.50 };
          const inTok = Math.round(messages.reduce((n, m) => n + (m.content || '').length, 0) / 4);
          const outTok = Math.round(fullText.length / 4);
          const cost = (inTok * p.inp + outTok * p.out) / 1e6;
          footer = `<div class="llm-cost-footer">💶 <strong>€${cost.toFixed(4)}</strong> (est.) · ${(inTok + outTok).toLocaleString()} tok · ${elapsed}s</div>`;
        }
        contentEl.innerHTML = formatMarkdown(fullText) + footer;
      }
      return fullText;
    };

    const [resultA, resultB] = await Promise.all([
      runModel(modelA, contentA, timeA),
      runModel(modelB, contentB, timeB),
    ]);

    return { a: resultA, b: resultB };
  },
};
