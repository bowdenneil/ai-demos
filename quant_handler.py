#!/usr/bin/env python3
"""
Quant Arena backend handler — imported by server.py.
Handles /api/quant/* endpoints for the A/B model comparison demo.
"""
import json
import os
import time
import urllib.request
import urllib.parse
from urllib.parse import urlparse, parse_qs

# These will be injected by server.py
_API_KEY = None
_API_BASE = None
_ANTHROPIC_KEY = None

def init(api_key, api_base, anthropic_key=None):
    global _API_KEY, _API_BASE, _ANTHROPIC_KEY
    _API_KEY = api_key
    _API_BASE = api_base
    _ANTHROPIC_KEY = anthropic_key

def _get_anthropic_key():
    return _ANTHROPIC_KEY or ''


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
    except:
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


def _run_single(handler, data, qd):
    """Run a single model on a scenario, streaming via SSE."""
    scenario_id = data.get('scenario', 'yield_curve')
    model_api_name = data.get('model', 'deepseek-ai/DeepSeek-V3.2')
    label = data.get('label', 'A')
    
    scenario = qd.SCENARIOS.get(scenario_id, qd.SCENARIOS['yield_curve'])
    market_data_json = qd.build_market_data_json(scenario_id)
    
    system_msg = {
        'role': 'system',
        'content': scenario['prompt']
    }
    user_msg = {
        'role': 'user',
        'content': f'Here is the current market data. Analyse it and write Python code as instructed.\n\n```json\n{market_data_json}\n```'
    }
    
    # Send SSE headers
    handler.send_response(200)
    handler.send_cors_headers()
    handler.send_header('Content-Type', 'text/event-stream')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()
    
    def send_event(payload):
        handler.wfile.write(f'data: {json.dumps(payload)}\n\n'.encode())
        handler.wfile.flush()
    
    try:
        req_data = json.dumps({
            'model': model_api_name,
            'messages': [system_msg, user_msg],
            'stream': True,
            'max_tokens': 4096,
        }).encode()
        
        # Route to Anthropic if model starts with "anthropic/"
        if model_api_name.startswith('anthropic/'):
            anthropic_model = model_api_name.replace('anthropic/', '')
            # Convert to Anthropic Messages API format
            system_content = system_msg['content']
            conv_messages = [{'role': 'user', 'content': user_msg['content']}]
            anthropic_req = json.dumps({
                'model': anthropic_model,
                'max_tokens': 4096,
                'messages': conv_messages,
                'stream': True,
                'system': system_content,
            }).encode()
            
            # We'll use the server's proxy by calling /api/chat/completions
            # which already handles Anthropic routing. But since quant_handler
            # runs server-side, we call Anthropic directly.
            _ANTHROPIC_KEY = _get_anthropic_key()
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=anthropic_req,
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': _ANTHROPIC_KEY,
                    'anthropic-version': '2023-06-01',
                },
                method='POST'
            )
            resp = urllib.request.urlopen(req, timeout=300)
            
            full_text = ''
            token_count = 0
            start_time = time.time()
            
            # Parse Anthropic SSE stream
            buffer = ''
            for chunk in iter(lambda: resp.read(4096), b''):
                buffer += chunk.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line.startswith('data: '):
                        continue
                    try:
                        event = json.loads(line[6:])
                        if event.get('type') == 'content_block_delta':
                            delta = event.get('delta', {})
                            text = delta.get('text', '')
                            if text:
                                full_text += text
                                token_count += 1
                                send_event({'type': 'stream', 'label': label, 'text': full_text, 'tokens': token_count})
                    except:
                        continue
            
            elapsed = round(time.time() - start_time, 2)
            
        else:
            req = urllib.request.Request(
                f'{_API_BASE}/chat/completions',
                data=req_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {_API_KEY}',
                },
            method='POST'
        )
        
        resp = urllib.request.urlopen(req, timeout=300)
        full_text = ''
        token_count = 0
        start_time = time.time()
        
        for line in resp:
            line = line.decode('utf-8').strip()
            if not line.startswith('data: ') or line == 'data: [DONE]':
                continue
            try:
                chunk = json.loads(line[6:])
                delta = chunk.get('choices', [{}])[0].get('delta', {})
                text = delta.get('content', '')
                reasoning = delta.get('reasoning_content', '')
                
                if reasoning:
                    # Accumulate reasoning into full_text too — some models (GLM-5.2) 
                    # output their entire response as reasoning_content with no content field
                    full_text += reasoning
                    token_count += 1
                    send_event({'type': 'reasoning', 'label': label, 'text': full_text[-500:], 'tokens': token_count})
                
                if text:
                    full_text += text
                    token_count += 1
                    send_event({'type': 'stream', 'label': label, 'text': full_text, 'tokens': token_count})
            except:
                continue
        
        elapsed = round(time.time() - start_time, 2)
        
        # Execute the generated code
        # If code block is open but not closed (model ran out of tokens), try anyway
        has_complete_code = full_text.count('```') >= 2 or ('```python' in full_text and full_text.rstrip().endswith('```'))
        if not has_complete_code and '```python' in full_text:
            # Code block is open but not closed — append closing backticks and try
            full_text = full_text.rstrip() + '\n```'
            has_complete_code = True
        
        if has_complete_code:
            code_result = qd.execute_generated_code(full_text, market_data_json)
        else:
            code_result = {'success': False, 'output': '', 'chart_data': None, 'error': 'No code block found in response', 'execution_time': 0}
        
        # Get model cost info
        model_info = qd.get_model_info(model_api_name)
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
