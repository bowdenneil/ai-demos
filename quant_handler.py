#!/usr/bin/env python3
"""
Quant Arena backend handler — imported by server.py.
Handles /api/quant/* endpoints for the A/B model comparison demo.
"""
import json
import time
import urllib.request

# Injected by server.py
_API_KEY = None
_API_BASE = None
_ANTHROPIC_KEY = None


def init(api_key, api_base, anthropic_key=None):
    global _API_KEY, _API_BASE, _ANTHROPIC_KEY
    _API_KEY = api_key
    _API_BASE = api_base
    _ANTHROPIC_KEY = anthropic_key


def handle_get(handler, path, params):
    """Handle GET /api/quant/* requests."""
    import quant_data as qd

    if path == '/api/quant/scenarios':
        handler.send_json_response(200, {'scenarios': qd.get_scenarios()})
        return True

    elif path == '/api/quant/models':
        handler.send_json_response(200, {'models': qd.list_available_models()})
        return True

    elif path == '/api/quant/data':
        scenario_id = params.get('scenario', ['yield_curve'])[0]
        data = qd.get_scenario_data(scenario_id)
        handler.send_json_response(200, data)
        return True

    return False


def handle_post(handler, path, body):
    """Handle POST /api/quant/* requests."""
    import quant_data as qd

    try:
        data = json.loads(body) if body else {}
    except ValueError:
        data = {}

    if path == '/api/quant/execute':
        code = data.get('code', '')
        market_data_json = data.get('market_data', '{}')
        result = qd.execute_generated_code(code, market_data_json)
        handler.send_json_response(200, result)
        return True

    elif path == '/api/quant/run':
        _run_single(handler, data, qd)
        return True

    return False


def _stream_anthropic(model, system_msg, user_msg, on_text):
    """Stream from Anthropic Messages API. Returns (full_text, chunk_count)."""
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=json.dumps({
            'model': model,
            'max_tokens': 4096,
            'system': system_msg['content'],
            'messages': [{'role': 'user', 'content': user_msg['content']}],
            'stream': True,
        }).encode(),
        headers={
            'Content-Type': 'application/json',
            'x-api-key': _ANTHROPIC_KEY or '',
            'anthropic-version': '2023-06-01',
        },
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=300)
    full_text, chunks = '', 0
    for raw in resp:
        line = raw.decode('utf-8').strip()
        if not line.startswith('data: '):
            continue
        try:
            event = json.loads(line[6:])
        except ValueError:
            continue
        if event.get('type') == 'content_block_delta':
            text = event.get('delta', {}).get('text', '')
            if text:
                full_text += text
                chunks += 1
                on_text(full_text, chunks, False)
    return full_text, chunks


def _stream_tensorx(model, system_msg, user_msg, on_text):
    """Stream from Tensorx (OpenAI-compatible). Returns (full_text, chunk_count)."""
    req = urllib.request.Request(
        f'{_API_BASE}/chat/completions',
        data=json.dumps({
            'model': model,
            'messages': [system_msg, user_msg],
            'stream': True,
            'max_tokens': 4096,
        }).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {_API_KEY}',
        },
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=300)
    full_text, chunks = '', 0
    for raw in resp:
        line = raw.decode('utf-8').strip()
        if not line.startswith('data: ') or line == 'data: [DONE]':
            continue
        try:
            chunk = json.loads(line[6:])
        except ValueError:
            continue
        delta = chunk.get('choices', [{}])[0].get('delta', {})
        # Some models (GLM) emit everything as reasoning_content with no content
        text = delta.get('content', '') or delta.get('reasoning_content', '')
        is_reasoning = not delta.get('content') and bool(delta.get('reasoning_content'))
        if text:
            full_text += text
            chunks += 1
            on_text(full_text, chunks, is_reasoning)
    return full_text, chunks


def _repair_code(model_api_name, full_text, error, market_data_json, qd):
    """One-shot code repair: send the error back to the model, re-execute."""
    # Describe the actual data structure so the fix targets reality, not memory
    try:
        md = json.loads(market_data_json)
        keys = [k for k in md.keys() if not k.startswith('_')]
        shape_desc = (f"top-level keys: {keys}. Each series key maps to "
                      "{'name': str, 'unit': str, 'dates': list[str], 'values': list[float]}")
    except Exception:
        shape_desc = 'unknown'

    fix_prompt = {
        'role': 'user',
        'content': (
            'Your Python code failed with this error:\n\n'
            f'{error}\n\n'
            f'The market_data dict has this exact structure: {shape_desc}\n\n'
            'Return ONLY the corrected complete Python code in a single ```python block. '
            'No explanations. Rules:\n'
            '- market_data is a dict already in scope\n'
            '- wrap lists with pd.Series/np.array before pandas/numpy ops\n'
            '- pandas 2.x+: use .ffill()/.bfill(), NOT fillna(method=...)\n'
            '- use .iloc for positional indexing, not [0] on Series\n'
            '- set chart_data (JSON-serializable dict) at the end'
        )
    }
    sys_msg = {'role': 'system', 'content': 'You are a quant developer. Fix the broken code. Reply with only a ```python code block.'}
    prev = {'role': 'assistant', 'content': full_text[-3000:]}

    try:
        if model_api_name.startswith('anthropic/'):
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=json.dumps({
                    'model': model_api_name.replace('anthropic/', ''),
                    'max_tokens': 2048,
                    'system': sys_msg['content'],
                    'messages': [prev, fix_prompt],
                }).encode(),
                headers={'Content-Type': 'application/json', 'x-api-key': _ANTHROPIC_KEY or '',
                         'anthropic-version': '2023-06-01'},
                method='POST')
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
            fixed = ''.join(b.get('text', '') for b in resp.get('content', []))
        else:
            req = urllib.request.Request(
                f'{_API_BASE}/chat/completions',
                data=json.dumps({
                    'model': model_api_name,
                    'messages': [sys_msg, prev, fix_prompt],
                    'max_tokens': 2048,
                }).encode(),
                headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {_API_KEY}'},
                method='POST')
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
            fixed = resp.get('choices', [{}])[0].get('message', {}).get('content', '')

        if '```' in fixed:
            return qd.execute_generated_code(fixed, market_data_json), fixed
    except Exception:
        pass
    return None, None


def _run_single(handler, data, qd):
    """Run a single model on a scenario, streaming via SSE."""
    scenario_id = data.get('scenario', 'yield_curve')
    model_api_name = data.get('model', 'deepseek/deepseek-v4-flash-0731')
    label = data.get('label', 'A')

    scenario = qd.SCENARIOS.get(scenario_id, qd.SCENARIOS['yield_curve'])
    market_data_json = qd.build_market_data_json(scenario_id)

    system_msg = {'role': 'system', 'content': scenario['prompt']}
    user_msg = {
        'role': 'user',
        'content': f'Here is the current market data. Analyse it and write Python code as instructed.\n\n```json\n{market_data_json}\n```'
    }

    handler.send_response(200)
    handler.send_cors_headers()
    handler.send_header('Content-Type', 'text/event-stream')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('Connection', 'close')  # SSE has no length — close so clients see EOF
    handler.end_headers()

    def send_event(payload):
        handler.wfile.write(f'data: {json.dumps(payload)}\n\n'.encode())
        handler.wfile.flush()

    model_info = qd.get_model_info(model_api_name)

    # Tell the UI which model is actually running (server truth)
    send_event({
        'type': 'start', 'label': label,
        'model': model_api_name,
        'model_name': model_info['name'],
        'model_type': model_info['type'],
    })

    def on_text(full_text, chunks, is_reasoning):
        etype = 'reasoning' if is_reasoning else 'stream'
        text = full_text[-500:] if is_reasoning else full_text
        send_event({'type': etype, 'label': label, 'text': text, 'tokens': chunks})

    try:
        start_time = time.time()
        if model_api_name.startswith('anthropic/'):
            full_text, chunk_count = _stream_anthropic(
                model_api_name.replace('anthropic/', ''), system_msg, user_msg, on_text)
        else:
            full_text, chunk_count = _stream_tensorx(
                model_api_name, system_msg, user_msg, on_text)
        elapsed = round(time.time() - start_time, 2)

        # Estimate real tokens (~4 chars/token) — chunk count under-reports
        token_count = max(chunk_count, len(full_text) // 4)

        # Execute the generated code. If the code block is open but unclosed
        # (model ran out of tokens), close it and try anyway.
        has_complete_code = full_text.count('```') >= 2
        if not has_complete_code and '```python' in full_text:
            full_text = full_text.rstrip() + '\n```'
            has_complete_code = True

        if has_complete_code:
            code_result = qd.execute_generated_code(full_text, market_data_json)
            # Self-repair: feed the error back to the model, up to 2 rounds
            attempt = 0
            repair_ctx = full_text  # what the model sees as its previous attempt
            while not code_result.get('success') and attempt < 2:
                attempt += 1
                send_event({'type': 'repairing', 'label': label,
                            'error': code_result.get('error', ''), 'attempt': attempt})
                fixed_result, fixed_code = _repair_code(
                    model_api_name, repair_ctx, code_result.get('error', ''), market_data_json, qd)
                if fixed_result is None:
                    break  # repair call itself failed — keep original error
                if fixed_code:
                    repair_ctx = fixed_code  # next round repairs the repaired code
                code_result = fixed_result
                if code_result.get('success'):
                    code_result['repaired'] = True
        else:
            code_result = {'success': False, 'output': '', 'chart_data': None,
                           'error': 'No code block found in response', 'execution_time': 0}

        cost = (token_count / 1000000) * model_info['cost_output']

        send_event({
            'type': 'complete',
            'label': label,
            'full_text': full_text,
            'tokens': token_count,
            'elapsed': elapsed,
            'model': model_api_name,
            'model_name': model_info['name'],
            'model_type': model_info['type'],
            'cost': round(cost, 4),
            'code_result': code_result,
        })

        handler.wfile.write(b'data: [DONE]\n\n')
        handler.wfile.flush()

    except Exception as e:
        send_event({'type': 'error', 'label': label, 'error': str(e)})
        handler.wfile.write(b'data: [DONE]\n\n')
        handler.wfile.flush()
