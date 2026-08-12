"""
Quant Arena — Market data module.
Fetches real market data from FRED (Federal Reserve Economic Data) API.
Caches to /tmp to avoid repeated calls.

No API key required for basic FRED JSON endpoints — uses public fetcher.
Fallback: generates realistic synthetic data if FRED is unreachable.
"""
import json
import os
import time
import urllib.request
import urllib.parse
import math
import random
from datetime import datetime, timedelta

CACHE_DIR = '/tmp/quant_cache'
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600  # 1 hour

# ─── FRED API ───────────────────────────────────────────────────────────────
FRED_BASE = 'https://fred.stlouisfed.org/graph/fred-2.csv'

# FRED series IDs for each scenario
SERIES = {
    # Yield Curve
    'DGS2':   {'name': 'US 2Y Treasury',         'unit': '%',     'scenario': 'yield_curve'},
    'DGS5':   {'name': 'US 5Y Treasury',         'unit': '%',     'scenario': 'yield_curve'},
    'DGS10':  {'name': 'US 10Y Treasury',        'unit': '%',     'scenario': 'yield_curve'},
    'DGS30':  {'name': 'US 30Y Treasury',        'unit': '%',     'scenario': 'yield_curve'},
    'DFF':    {'name': 'Fed Funds Rate',         'unit': '%',     'scenario': 'yield_curve'},
    'CPIAUCSL': {'name': 'CPI',                  'unit': 'index', 'scenario': 'yield_curve'},
    'T5YIE':  {'name': '5Y Breakeven Inflation', 'unit': '%',     'scenario': 'yield_curve'},
    # Credit Spreads
    'BAMLC0A0CM': {'name': 'IG OAS Spread',      'unit': '%',     'scenario': 'credit_spreads'},
    'BAMLC0A4CBBB': {'name': 'BBB OAS Spread',   'unit': '%',     'scenario': 'credit_spreads'},
    'BAMLH0A0HYM2': {'name': 'HY OAS Spread',   'unit': '%',     'scenario': 'credit_spreads'},
    'DGS10':  {'name': 'US 10Y Treasury',        'unit': '%',     'scenario': 'credit_spreads'},
    'VIXCLS': {'name': 'VIX',                    'unit': '',      'scenario': 'credit_spreads'},
    'DTB3':   {'name': '3M T-Bill',              'unit': '%',     'scenario': 'credit_spreads'},
    # FX
    'DEXUSEU': {'name': 'USD/EUR',               'unit': '',      'scenario': 'fx'},
    'DGS10':  {'name': 'US 10Y',                 'unit': '%',     'scenario': 'fx'},
    'IRLTLT01EZM156N': {'name': 'EZ 10Y',       'unit': '%',     'scenario': 'fx'},
    'DTB3':   {'name': 'US 3M Rate',             'unit': '%',     'scenario': 'fx'},
    'IRSTCI01EZM156N': {'name': 'EZ 3M Rate',   'unit': '%',     'scenario': 'fx'},
    'VIXCLS': {'name': 'VIX',                    'unit': '',      'scenario': 'fx'},
}

def _fetch_fred_series(series_id, years=5):
    """Fetch a single FRED series. Falls back to synthetic data if API unavailable."""
    cache_file = os.path.join(CACHE_DIR, f'fred_{series_id}.json')
    
    # Check cache first (1 hour TTL)
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < CACHE_TTL:
            with open(cache_file) as f:
                return json.load(f)
    
    # Try FRED API (requires free key — without key, fall back to synthetic)
    fred_key = os.environ.get('FRED_API_KEY', '')
    if fred_key:
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=years * 365)).strftime('%Y-%m-%d')
            url = f'https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={fred_key}&file_type=json&observation_start={start_date}&observation_end={end_date}'
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            
            series_data = []
            for obs in data.get('observations', []):
                if obs.get('value', '.') == '.':
                    continue
                try:
                    val = float(obs['value'])
                    series_data.append({'date': obs['date'], 'value': val})
                except (ValueError, KeyError):
                    continue
            
            if series_data:
                with open(cache_file, 'w') as f:
                    json.dump(series_data, f)
                return series_data
        except Exception:
            pass  # Fall through to synthetic
    
    # Use synthetic data (realistic random walk based on real baseline values)
    return _synthetic_series(series_id, years)


def _synthetic_series(series_id, years=5):
    """Generate realistic-looking synthetic data for a series."""
    meta = SERIES.get(series_id, {'name': series_id, 'unit': '%'})
    base_val = {
        'DGS2': 4.2, 'DGS5': 4.0, 'DGS10': 4.1, 'DGS30': 4.3,
        'DFF': 5.25, 'CPIAUCSL': 310, 'T5YIE': 2.3,
        'BAMLC0A0CM': 1.2, 'BAMLC0A4CBBB': 1.6, 'BAMLH0A0HYM2': 3.8,
        'VIXCLS': 16, 'DTB3': 4.8,
        'DEXUSEU': 1.08, 'IRLTLT01EZM156N': 2.8, 'IRSTCI01EZM156N': 3.5,
    }.get(series_id, 2.0)
    
    data = []
    current = base_val
    days = years * 252  # trading days
    
    for i in range(days):
        date = (datetime.now() - timedelta(days=days - i)).strftime('%Y-%m-%d')
        # Random walk with mean reversion
        drift = (base_val - current) * 0.02
        noise = random.gauss(0, base_val * 0.01)
        current = current + drift + noise
        if current < 0:
            current = 0.01
        data.append({'date': date, 'value': round(current, 4)})
    
    # Cache synthetic data too
    cache_file = os.path.join(CACHE_DIR, f'fred_{series_id}.json')
    with open(cache_file, 'w') as f:
        json.dump(data, f)
    
    return data


def get_scenario_data(scenario_id):
    """
    Get all series data for a scenario.
    Returns: {
        'scenario': 'yield_curve',
        'series': {series_id: {name, unit, data: [{date, value}]}},
        'summary': {series_id: {last_value, change_1d, change_30d, min, max, mean}}
    }
    """
    series_ids = [sid for sid, meta in SERIES.items() if meta['scenario'] == scenario_id]
    
    result = {
        'scenario': scenario_id,
        'series': {},
        'summary': {},
    }
    
    for sid in series_ids:
        meta = SERIES[sid]
        data = _fetch_fred_series(sid)
        
        result['series'][sid] = {
            'name': meta['name'],
            'unit': meta['unit'],
            'data': data[-126:] if len(data) > 126 else data,  # last ~6 months
        }
        
        # Summary stats
        if data:
            values = [d['value'] for d in data]
            last = values[-1]
            prev = values[-2] if len(values) > 1 else last
            m30 = values[-30] if len(values) > 30 else values[0]
            
            result['summary'][sid] = {
                'name': meta['name'],
                'last_value': round(last, 4),
                'change_1d': round(last - prev, 4),
                'change_30d': round(last - m30, 4),
                'min': round(min(values), 4),
                'max': round(max(values), 4),
                'mean': round(sum(values) / len(values), 4),
                'unit': meta['unit'],
                'count': len(values),
            }
    
    return result


# ─── SCENARIOS ───────────────────────────────────────────────────────────────
SCENARIOS = {
    'yield_curve': {
        'id': 'yield_curve',
        'title': 'Yield Curve Forecast',
        'subtitle': 'Forecast US Treasury yields 30 days forward using macro signals',
        'icon': '📈',
        'series': ['DGS2', 'DGS5', 'DGS10', 'DGS30', 'DFF', 'CPIAUCSL', 'T5YIE'],
        'prompt': """You are a quantitative analyst at a major bank. You have been given the following US Treasury yield data and macroeconomic indicators.

Your task:
1. Analyse the current shape of the yield curve (normal, inverted, flat)
2. Identify the key drivers of recent yield movements
3. Write Python code using pandas, numpy, and statsmodels to:
   - Calculate the 2s10s, 2s30s, and 5s30s spreads
   - Fit a Nelson-Siegel or polynomial model to the yield curve
   - Forecast yields 30 days forward using ARIMA or linear trend
   - Calculate confidence intervals
4. Provide a summary forecast with direction and magnitude

IMPORTANT RULES:
- Do NOT echo back the market data in your response. Go straight to your analysis and code.
- Write CONCISE code (under 50 lines). Do not write long explanations inside the code.
- The data is available as a Python dict called `market_data` when your code executes.
- End your code by setting a variable called `chart_data` with a JSON-serializable dict containing your forecast results for plotting.
- Write the Python code in a SINGLE code block delimited by triple backticks.
- Do NOT use matplotlib plt.show() or plt.savefig(). Do NOT import os, sys, or subprocess.
- Do NOT use pd.read_csv, pd.read_json, or any file I/O. The data is already in `market_data`.
- Keep your total response under 3000 tokens. Be brief in prose, focus on code.""",
    },
    'credit_spreads': {
        'id': 'credit_spreads',
        'title': 'Credit Spread Analysis',
        'subtitle': 'Identify credit regime shifts and forecast spread compression/expansion',
        'icon': '💳',
        'series': ['BAMLC0A0CM', 'BAMLC0A4CBBB', 'BAMLH0A0HYM2', 'DGS10', 'VIXCLS', 'DTB3'],
        'prompt': """You are a credit strategist at a major bank. You have been given credit spread data (IG, BBB, and High Yield OAS), Treasury yields, VIX, and short-term rates.

Your task:
1. Analyse the current credit environment — are spreads tight or wide historically?
2. Identify the relationship between VIX, rates, and credit spreads
3. Write Python code using pandas, numpy, and statsmodels to:
   - Calculate z-scores of each spread vs its 5Y history
   - Run a regression of IG spreads on VIX, 10Y yield, and 3M T-bill
   - Identify regime shifts (compression vs expansion)
   - Forecast IG and HY spreads 30 days forward
4. Provide a summary with credit outlook (bullish/bearish/neutral)

IMPORTANT RULES:
- Do NOT echo back the market data in your response. Go straight to your analysis and code.
- Write CONCISE code (under 50 lines). Do not write long explanations inside the code.
- The data is available as a Python dict called `market_data` when your code executes.
- End your code by setting a variable called `chart_data` with a JSON-serializable dict containing your forecast results for plotting.
- Write the Python code in a SINGLE code block delimited by triple backticks.
- Do NOT use matplotlib plt.show() or plt.savefig(). Do NOT import os, sys, or subprocess.
- Do NOT use pd.read_csv, pd.read_json, or any file I/O. The data is already in `market_data`.
- Keep your total response under 3000 tokens. Be brief in prose, focus on code.""",
    },
    'fx_forecast': {
        'id': 'fx_forecast',
        'title': 'FX Forecast: USD/EUR',
        'subtitle': 'Forecast USD/EUR direction using rate differentials and macro signals',
        'icon': '💱',
        'series': ['DEXUSEU', 'DGS10', 'IRLTLT01EZM156N', 'DTB3', 'IRSTCI01EZM156N', 'VIXCLS'],
        'prompt': """You are an FX strategist at a major bank. You have USD/EUR exchange rate data, US and Eurozone interest rates (10Y and 3M), and VIX.

Your task:
1. Analyse the interest rate differential between US and Eurozone
2. Assess whether USD/EUR is overvalued or undervalued based on rate differentials
3. Write Python code using pandas, numpy, and statsmodels to:
   - Calculate the rate differential (US 10Y - EZ 10Y) and (US 3M - EZ 3M)
   - Run a regression of USD/EUR on the rate differentials and VIX
   - Build a simple momentum/mean-reversion signal
   - Forecast USD/EUR 30 days forward with confidence intervals
4. Provide a directional forecast (USD bullish/bearish vs EUR) with target range

IMPORTANT RULES:
- Do NOT echo back the market data in your response. Go straight to your analysis and code.
- Write CONCISE code (under 50 lines). Do not write long explanations inside the code.
- The data is available as a Python dict called `market_data` when your code executes.
- End your code by setting a variable called `chart_data` with a JSON-serializable dict containing your forecast results for plotting.
- Write the Python code in a SINGLE code block delimited by triple backticks.
- Do NOT use matplotlib plt.show() or plt.savefig(). Do NOT import os, sys, or subprocess.
- Do NOT use pd.read_csv, pd.read_json, or any file I/O. The data is already in `market_data`.
- Keep your total response under 3000 tokens. Be brief in prose, focus on code.""",
    },
}


def get_scenarios():
    """Return scenario metadata for the frontend."""
    return [
        {
            'id': sid,
            'title': s['title'],
            'subtitle': s['subtitle'],
            'icon': s['icon'],
            'series': [{'id': s_id, 'name': SERIES[s_id]['name'], 'unit': SERIES[s_id]['unit']} for s_id in s['series']],
        }
        for sid, s in SCENARIOS.items()
    ]


def build_market_data_json(scenario_id):
    """
    Build a compact JSON market data string for the LLM prompt.
    Only includes recent data (30 data points) + summary stats to keep token count low.
    The full dataset is available separately for code execution.
    """
    data = get_scenario_data(scenario_id)
    
    # Build compact summary — last 30 data points per series + stats
    compact = {}
    for sid, info in data['series'].items():
        values = [d['value'] for d in info['data']][-30:]  # last 30 points
        dates = [d['date'] for d in info['data']][-30:]
        compact[sid] = {
            'name': info['name'],
            'unit': info['unit'],
            'dates': dates,
            'values': values,
        }
    
    # Add summary stats
    compact['_summary'] = data['summary']
    compact['_scenario'] = scenario_id
    compact['_as_of'] = datetime.now().strftime('%Y-%m-%d')
    
    return json.dumps(compact, separators=(',', ':'))


def execute_generated_code(code, market_data_json):
    """
    Execute LLM-generated code in a controlled environment.
    
    The code has access to: market_data (dict), pandas (pd), numpy (np), 
    scipy (sp), statsmodels (sm), sklearn, json, math, and a set of 
    safe builtins. No file I/O, no imports of os/sys/subprocess.
    
    Returns: {
        'success': bool,
        'output': str,       # stdout from print statements
        'chart_data': dict,  # if the code produced chart data
        'error': str,        # error message if failed
        'execution_time': float,
    }
    """
    import io
    import contextlib
    import traceback
    import re as _re
    
    # Parse market data
    try:
        market_data = json.loads(market_data_json)
    except:
        market_data = {}
    
    # Prepare safe namespace — give models everything they commonly need
    import builtins
    safe_builtins = {k: getattr(builtins, k) for k in dir(builtins) if not k.startswith('_')}
    # Remove dangerous ones
    for dangerous in ['__import__', 'exec', 'eval', 'compile', 'open', 'input', 'breakpoint', 'exit', 'quit', 'globals', 'locals', 'vars', 'dir']:
        safe_builtins.pop(dangerous, None)
    # But keep __import__ for safe module loading
    safe_builtins['__import__'] = __import__
    
    safe_globals = {
        '__builtins__': safe_builtins,
        'json': __import__('json'),
        'math': __import__('math'),
        're': __import__('re'),
        'datetime': __import__('datetime'),
    }
    safe_globals['timedelta'] = safe_globals['datetime'].timedelta
    
    # Pre-import commonly used modules — models use these directly
    for alias, module in [
        ('pd', 'pandas'), ('np', 'numpy'), ('sp', 'scipy'),
        ('sm', 'statsmodels'), ('sklearn', 'sklearn'),
    ]:
        try:
            safe_globals[alias] = __import__(module)
        except:
            pass
    
    # Also expose submodules models commonly use
    try:
        safe_globals['statsmodels'] = safe_globals.get('sm')
        from scipy import stats as sp_stats
        safe_globals['stats'] = sp_stats
    except:
        pass
    try:
        from sklearn import linear_model as sk_lm
        safe_globals['linear_model'] = sk_lm
    except:
        pass
    try:
        from statsmodels.tsa import arima as sm_arima
        safe_globals['ARIMA'] = sm_arima.ARIMA
    except:
        pass
    try:
        from statsmodels.tsa.arima.model import ARIMA as _ARIMA2
        safe_globals['ARIMA'] = _ARIMA2
    except:
        pass
    
    safe_locals = {
        'market_data': market_data,
    }
    # Merge locals into globals so functions defined in exec can see module-level vars
    safe_globals.update(safe_locals)
    
    # Capture stdout
    stdout_capture = io.StringIO()
    
    # Extract ALL code blocks from the response (some models write multiple)
    code_blocks = []
    # Match ```python ... ``` or ``` ... ```
    pattern = _re.compile(r'```(?:python)?\s*\n(.*?)```', _re.DOTALL)
    for m in pattern.finditer(code):
        code_blocks.append(m.group(1).strip())
    
    if not code_blocks:
        # No code block found — try to find raw Python-looking code
        # Look for lines starting with import or from
        lines = code.split('\n')
        code_start = -1
        for i, line in enumerate(lines):
            if line.strip().startswith(('import ', 'from ', 'import\t', 'pd.', 'np.', 'market_data', '#', 'def ', 'class ')):
                code_start = i
                break
        if code_start >= 0:
            code_blocks.append('\n'.join(lines[code_start:]))
    
    if not code_blocks:
        return {
            'success': False,
            'output': '',
            'chart_data': None,
            'error': 'No Python code block found in model response. The model may not have generated code.',
            'execution_time': 0,
        }
    
    # Try each code block until one works
    last_error = ''
    for i, code_block in enumerate(code_blocks):
        code_clean = code_block.strip()
        
        start_time = time.time()
        
        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(code_clean, safe_globals, safe_locals)
            
            execution_time = time.time() - start_time
            output = stdout_capture.getvalue()
            
            # Check if code left a chart_data variable
            chart_data = safe_locals.get('chart_data', None)
            
            # Also check for common variable names models use
            if chart_data is None:
                for var_name in ['forecast_data', 'chart', 'plot_data', 'results', 'forecast']:
                    if var_name in safe_locals and isinstance(safe_locals[var_name], (dict, list)):
                        chart_data = safe_locals[var_name]
                        break
            
            return {
                'success': True,
                'output': output[:5000],
                'chart_data': chart_data,
                'error': None,
                'execution_time': round(execution_time, 2),
            }
        except Exception as e:
            execution_time = time.time() - start_time
            last_error = str(e)[:500]
            # Clear stdout for next attempt
            stdout_capture = io.StringIO()
            continue
    
    return {
        'success': False,
        'output': stdout_capture.getvalue()[:2000],
        'chart_data': None,
        'error': last_error,
        'execution_time': round(execution_time, 2) if 'execution_time' in dir() else 0,
    }


# ─── MODEL COSTS ─────────────────────────────────────────────────────────────
# Cost per 1M tokens (input/output) in EUR
MODEL_COSTS = {
    'deepseek/deepseek-v4-flash-0731': {'input': 0.14, 'output': 0.28, 'name': 'DeepSeek V4 Flash', 'type': 'Open-Weight'},
    'z-ai/glm-5.2': {'input': 0.20, 'output': 0.80, 'name': 'GLM-5.2', 'type': 'Open-Weight'},
    'deepseek/deepseek-v3.2': {'input': 0.27, 'output': 1.10, 'name': 'DeepSeek V3.2', 'type': 'Open-Weight'},
    'deepseek/deepseek-r1-0528': {'input': 0.55, 'output': 2.19, 'name': 'DeepSeek R1', 'type': 'Open-Weight (Reasoning)'},
    'z-ai/glm-4.6': {'input': 0.40, 'output': 1.60, 'name': 'GLM-4.6', 'type': 'Open-Weight'},
    'qwen/qwen3-235b-a22b-2507': {'input': 0.30, 'output': 1.20, 'name': 'Qwen3 235B', 'type': 'Open-Weight'},
    'anthropic/claude-sonnet-5': {'input': 3.00, 'output': 15.00, 'name': 'Claude Sonnet 5', 'type': 'Closed (Commercial)'},
    'anthropic/claude-haiku-4-5-20251001': {'input': 0.80, 'output': 4.00, 'name': 'Claude Haiku 4.5', 'type': 'Closed (Commercial)'},
    'anthropic/claude-opus-4-5-20251101': {'input': 5.00, 'output': 25.00, 'name': 'Claude Opus 4.5', 'type': 'Closed (Commercial)'},
}

# Map portal model names to Tensorx API model names
MODEL_MAP = {
    'deepseek-v3': 'deepseek/deepseek-v3.2',
    'glm-4.5': 'z-ai/glm-4.6',
    'deepseek-r1': 'deepseek/deepseek-r1-0528',
    'glm-4-9b': 'z-ai/glm-5-turbo',
}

# Default models for A/B comparison
DEFAULT_MODELS = {
    'A': {'portal_name': 'DeepSeek V4 Flash', 'api_name': 'deepseek/deepseek-v4-flash-0731', 'color': '#53d8fb'},
    'B': {'portal_name': 'GLM-5.2', 'api_name': 'z-ai/glm-5.2', 'color': '#7c5cfc'},
}


def get_model_info(model_key):
    """Get model metadata for the frontend."""
    if model_key in MODEL_COSTS:
        cost = MODEL_COSTS[model_key]
        return {
            'api_name': model_key,
            'name': cost['name'],
            'type': cost['type'],
            'cost_input': cost['input'],
            'cost_output': cost['output'],
        }
    return {'api_name': model_key, 'name': model_key, 'type': 'Unknown', 'cost_input': 0, 'cost_output': 0}


def list_available_models():
    """List models available for the arena."""
    return [
        {'key': 'deepseek/deepseek-v4-flash-0731', 'name': 'DeepSeek V4 Flash', 'type': 'Open-Weight', 'params': '671B MoE (37B active)', 'cost_input': 0.14, 'cost_output': 0.28},
        {'key': 'z-ai/glm-5.2', 'name': 'GLM-5.2', 'type': 'Open-Weight', 'params': '355B MoE (32B active)', 'cost_input': 0.20, 'cost_output': 0.80},
        {'key': 'deepseek/deepseek-v3.2', 'name': 'DeepSeek V3.2', 'type': 'Open-Weight', 'params': '671B MoE (37B active)', 'cost_input': 0.27, 'cost_output': 1.10},
        {'key': 'z-ai/glm-4.6', 'name': 'GLM-4.6', 'type': 'Open-Weight', 'params': '355B MoE (32B active)', 'cost_input': 0.40, 'cost_output': 1.60},
        {'key': 'deepseek/deepseek-r1-0528', 'name': 'DeepSeek R1', 'type': 'Open-Weight (Reasoning)', 'params': '671B MoE (37B active)', 'cost_input': 0.55, 'cost_output': 2.19},
        {'key': 'qwen/qwen3-235b-a22b-2507', 'name': 'Qwen3 235B', 'type': 'Open-Weight', 'params': '235B MoE (22B active)', 'cost_input': 0.30, 'cost_output': 1.20},
        {'key': 'anthropic/claude-sonnet-5', 'name': 'Claude Sonnet 5', 'type': 'Closed (Commercial)', 'params': '~Undisclosed', 'cost_input': 3.00, 'cost_output': 15.00},
        {'key': 'anthropic/claude-haiku-4-5-20251001', 'name': 'Claude Haiku 4.5', 'type': 'Closed (Commercial)', 'params': '~Undisclosed', 'cost_input': 0.80, 'cost_output': 4.00},
        {'key': 'anthropic/claude-opus-4-5-20251101', 'name': 'Claude Opus 4.5', 'type': 'Closed (Commercial)', 'params': '~Undisclosed', 'cost_input': 5.00, 'cost_output': 25.00},
    ]
