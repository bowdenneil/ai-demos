#!/usr/bin/env python3
"""
Local AI Demos server — serves the portal and proxies API calls to Tensorx.
This avoids CORS issues entirely since the browser talks to localhost.

Usage: python3 server.py [--port 8888] [--api-key YOUR_KEY]
"""
import http.server
import json
import os
import sys
import time
import random
import urllib.request
import urllib.error
import urllib.parse
import argparse
import sqlite3
import hashlib
import secrets
import threading
import base64
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

API_BASE = 'https://api.tensorx.ai/v1'
API_KEY = os.environ.get('TENSORX_API_KEY', '') or os.environ.get('TENSORIX_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_BASE = 'https://api.anthropic.com/v1'
BRAVE_KEY = os.environ.get('BRAVE_SEARCH_KEY', '')

# PiAPI for icon generation
PIAPI_KEY = os.environ.get('PIAPI_KEY', '')
ICON_DIR = Path(__file__).parent / 'icons'
ICON_PROMPTS = {
    'rag': 'Minimalist flat icon of an open book with digital data particles floating out, dark navy background, cyan glowing accents, simple clean vector style',
    'market': 'Minimalist flat icon of a magnifying glass over a growth chart, dark purple background, bright purple glowing accents, simple clean vector style',
    'finance': 'Minimalist flat icon of a euro symbol with upward trend arrow, dark rose background, pink glowing accents, simple clean vector style',
    'regulatory': 'Minimalist flat icon of a balance scale with a shield, dark emerald background, green glowing accents, simple clean vector style',
    'earnings': 'Minimalist flat icon of a rising bar chart with a microphone, dark amber background, orange glowing accents, simple clean vector style',
    'churn': 'Minimalist flat icon of circular arrows around a customer silhouette, dark orange background, bright orange glowing accents, simple clean vector style',
    'rfp': 'Minimalist flat icon of a document with a pen and checkmark, dark teal background, teal glowing accents, simple clean vector style',
    'image': 'Minimalist flat icon of an artists paint palette with a glowing brush stroke, dark purple-teal gradient background, teal and purple glowing accents, simple clean vector style',
    'onprem': 'Minimalist flat icon of a server rack with glowing GPU chips and a EU flag star, dark violet-blue gradient background, violet and blue glowing accents, simple clean vector style',
    'tco': 'Minimalist flat icon of a calculator with a euro symbol and bar chart, dark emerald-teal gradient background, emerald and cyan glowing accents, simple clean vector style',
    'network': 'Minimalist flat icon of a radio tower with signal waves and a network graph, dark blue-sky gradient background, blue and sky glowing accents, simple clean vector style',
    'swarm': 'Minimalist flat icon of three connected nodes forming a network with a central brain symbol, dark cyan-purple gradient background, cyan and purple glowing accents, simple clean vector style',
}

# ─── AUTH DATABASE ───
AUTH_DB_DIR = Path.home() / '.ai-demos'
AUTH_DB_PATH = AUTH_DB_DIR / 'auth.db'

def init_db():
    """Create auth database and tables if they don't exist."""
    AUTH_DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    # Login audit log — tracks every login attempt with IP + user-agent
    conn.execute('''CREATE TABLE IF NOT EXISTS login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        email TEXT NOT NULL,
        success INTEGER NOT NULL DEFAULT 0,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    conn.commit()

    # Seed admin user if not exists
    admin_email = 'neil.bowden@dell.com'
    row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
    if not row:
        salt = secrets.token_hex(16)
        password = 'PugHermes2026!'
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        conn.execute(
            'INSERT INTO users (email, password_hash, salt) VALUES (?, ?, ?)',
            (admin_email, password_hash, salt)
        )
        conn.commit()
        print(f'✓ Admin user created: {admin_email}')
    else:
        print(f'✓ Admin user exists: {admin_email}')

    # Seed guest user if not exists
    guest_email = 'guest@aidemos.com'
    row = conn.execute('SELECT id FROM users WHERE email = ?', (guest_email,)).fetchone()
    if not row:
        salt = secrets.token_hex(16)
        password = 'guest2026'
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        conn.execute(
            'INSERT INTO users (email, password_hash, salt) VALUES (?, ?, ?)',
            (guest_email, password_hash, salt)
        )
        conn.commit()
        print(f'✓ Guest user created: {guest_email}')
    else:
        print(f'✓ Guest user exists: {guest_email}')

    # Seed John Bowden user if not exists
    john_email = 'j.bowden@waveguideltd.com'
    row = conn.execute('SELECT id FROM users WHERE email = ?', (john_email,)).fetchone()
    if not row:
        salt = secrets.token_hex(16)
        password = 'Waveguide2026!'
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        conn.execute(
            'INSERT INTO users (email, password_hash, salt) VALUES (?, ?, ?)',
            (john_email, password_hash, salt)
        )
        conn.commit()
        print(f'✓ John Bowden user created: {john_email}')
    else:
        print(f'✓ John Bowden user exists: {john_email}')

    # ── Onboarding employees table ──
    conn.execute('''CREATE TABLE IF NOT EXISTS onboarding_employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        role TEXT,
        department TEXT,
        start_date TEXT,
        location TEXT,
        manager TEXT,
        agent_tasks TEXT,
        welcome_packet TEXT,
        status TEXT DEFAULT 'onboarded',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.close()

def cleanup_sessions():
    """Delete expired sessions from the database."""
    try:
        conn = sqlite3.connect(str(AUTH_DB_PATH))
        conn.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'⚠ Session cleanup error: {e}')

def _get_db():
    """Get a new database connection."""
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def session_cleanup_timer():
    """Periodically clean up expired sessions."""
    cleanup_sessions()
    timer = threading.Timer(3600, session_cleanup_timer)
    timer.daemon = True
    timer.start()

def generate_icon_file(demo):
    """Generate an icon for the given demo using PiAPI gpt-image-1."""
    prompt = ICON_PROMPTS.get(demo)
    if not prompt:
        return

    icon_path = ICON_DIR / f'{demo}.png'
    if icon_path.exists():
        return

    try:
        print(f'  Generating icon for {demo}...')
        req_data = json.dumps({
            'model': 'gpt-image-1',
            'prompt': prompt,
            'size': '1024x1024',
            'n': 1,
            'response_format': 'b64_json'
        }).encode()

        req = urllib.request.Request(
            'https://api.piapi.ai/v1/images/generations',
            data=req_data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {PIAPI_KEY}',
                'User-Agent': 'AI-Demos-Portal/1.0'
            },
            method='POST'
        )

        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())

        # Extract base64 image data
        img_data = None
        if 'data' in data and len(data['data']) > 0:
            item = data['data'][0]
            if 'b64_json' in item:
                img_data = base64.b64decode(item['b64_json'])
            elif 'url' in item:
                # If URL format, download the image
                img_resp = urllib.request.urlopen(item['url'], timeout=30)
                img_data = img_resp.read()

        if img_data:
            ICON_DIR.mkdir(parents=True, exist_ok=True)
            icon_path.write_bytes(img_data)
            print(f'✓ Icon generated: {demo}.png ({len(img_data)} bytes)')
        else:
            print(f'⚠ No image data in response for {demo}')

    except Exception as e:
        print(f'⚠ Icon generation failed for {demo}: {e}')


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-AGENT RESEARCH SWARM
# ═══════════════════════════════════════════════════════════════════════════

import queue as _queue

SWARM_AGENTS = [
    {
        'id': 'market',
        'name': 'Market Researcher',
        'icon': '📊',
        'role': 'You are a market research specialist. You analyse market size, growth trends, competitive landscape, and customer segments. You provide data-driven insights with specific numbers and percentages.',
    },
    {
        'id': 'financial',
        'name': 'Financial Analyst',
        'icon': '💰',
        'role': 'You are a financial analyst. You evaluate revenue models, cost structures, margins, profitability, and investment implications. You think in terms of ROI, payback periods, and financial risk.',
    },
    {
        'id': 'risk',
        'name': 'Risk & Regulatory',
        'icon': '⚖️',
        'role': 'You are a risk and regulatory specialist. You identify regulatory barriers, compliance requirements, operational risks, and legal considerations. You think about what could go wrong and how to mitigate it.',
    },
    {
        'id': 'synthesis',
        'name': 'Synthesis Lead',
        'icon': '🧠',
        'role': 'You are the synthesis lead. You combine findings from other specialists into a cohesive executive briefing. You identify cross-cutting themes, resolve conflicts, and produce actionable recommendations.',
    },
]


def _llm_call(messages, model, api_key, max_tokens=2048):
    """Non-streaming LLM call to Tensorx. Returns the content string."""
    req_data = json.dumps({
        'model': model,
        'messages': messages,
        'stream': False,
        'max_tokens': max_tokens,
    }).encode()

    req = urllib.request.Request(
        f'{API_BASE}/chat/completions',
        data=req_data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=90)
    data = json.loads(resp.read())
    return data.get('choices', [{}])[0].get('message', {}).get('content', '')


def _brave_search(query, brave_key, count=6):
    """Search Brave and return simplified results."""
    if not brave_key:
        return []
    target = f'https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={count}'
    req = urllib.request.Request(target, headers={
        'Accept': 'application/json',
        'X-Subscription-Token': brave_key,
    })
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    return [
        {'title': r.get('title', ''), 'url': r.get('url', ''), 'description': r.get('description', '')}
        for r in (data.get('web', {}).get('results', []))
    ]


def _agent_worker(agent, query, model, api_key, brave_key, event_q, agent_idx, total, shared_sources):
    """Run a single specialist agent: search → reason → report.
    shared_sources: list to append {title, url} dicts for the final briefing.
    """
    aid = agent['id']
    aname = agent['name']

    try:
        # Phase 1: Planning
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'planning'})
        event_q.put({'type': 'agent_thinking', 'agent': aid,
                     'text': f'Analysing the query: "{query[:120]}..."\nDetermining what information I need to gather.'})

        # Phase 2: Web search — stagger to avoid Brave rate limits
        search_query = f'{query} {agent["role"].split(".")[1].strip()[:60] if "." in agent["role"] else ""}'
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'searching'})
        # Stagger search start by agent index to avoid 429s
        time.sleep(agent_idx * 1.5)
        results = _brave_search(query, brave_key)
        # Retry once if rate-limited
        if not results and brave_key:
            event_q.put({'type': 'agent_thinking', 'agent': aid, 'text': 'Search rate-limited, retrying...'})
            time.sleep(2)
            results = _brave_search(query, brave_key)

        # Stream search results
        for r in results[:4]:
            event_q.put({'type': 'agent_tool', 'agent': aid,
                         'tool': 'web_search', 'detail': r['title'], 'url': r['url']})
            time.sleep(0.15)  # visual pacing
            # Collect sources for the final briefing
            shared_sources.append({'title': r['title'], 'url': r['url']})

        # Build context from search results
        search_context = '\n'.join(
            f"[{i+1}] {r['title']}\n{r['description']}\nURL: {r['url']}"
            for i, r in enumerate(results[:6])
        ) if results else 'No web results available.'

        # Phase 3: LLM reasoning
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'reasoning'})
        event_q.put({'type': 'agent_thinking', 'agent': aid,
                     'text': f'Synthesising {len(results)} sources into specialist analysis...'})

        system_msg = agent['role'] + '\n\nYou are part of a multi-agent research team analysing the following query. Provide a focused, structured analysis from your specialist perspective. Use bullet points and specific data where possible. Keep it under 400 words.'

        user_msg = f'RESEARCH QUERY: {query}\n\nWEB SEARCH CONTEXT:\n{search_context}\n\nProvide your specialist analysis:'

        # Stream the reasoning by calling LLM and sending chunks
        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg},
        ]

        # Non-streaming call but simulate streaming for UX
        full_response = _llm_call(messages, model, api_key, max_tokens=2048)

        # Send response in ~3 chunks for visual streaming effect
        chunk_size = max(1, len(full_response) // 4)
        for i in range(0, len(full_response), chunk_size):
            chunk = full_response[i:i+chunk_size]
            event_q.put({'type': 'agent_chunk', 'agent': aid, 'text': chunk})
            time.sleep(0.08)

        # Phase 4: Complete
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'done'})
        event_q.put({'type': 'agent_result', 'agent': aid, 'text': full_response})

    except Exception as e:
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'error'})
        event_q.put({'type': 'agent_error', 'agent': aid, 'message': str(e)})


def _synthesis_worker(query, model, api_key, agent_results, event_q):
    """Run the synthesis agent after specialists complete."""
    aid = 'synthesis'
    try:
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'planning'})
        event_q.put({'type': 'agent_thinking', 'agent': aid,
                     'text': 'Collecting specialist reports and identifying cross-cutting themes...'})

        # Build context from all specialist results
        specialist_context = ''
        for agent in SWARM_AGENTS:
            if agent['id'] == 'synthesis':
                continue
            result = agent_results.get(agent['id'], '')
            specialist_context += f"\n\n{'='*60}\n{agent['icon']} {agent['name'].upper()}\n{'='*60}\n{result}"

        system_msg = (
            "You are the Synthesis Lead of a multi-agent research team. "
            "Below are specialist analyses from your team members. "
            "Synthesize them into a cohesive executive briefing with:\n"
            "1. **Executive Summary** — Key findings in 2-3 sentences\n"
            "2. **Strategic Insights** — Cross-cutting themes and patterns\n"
            "3. **Recommendations** — 3-5 actionable next steps\n"
            "4. **Risk Flags** — Key risks or conflicts identified\n"
            "5. **Confidence Assessment** — How confident is the team and why\n\n"
            "Use markdown formatting. Be specific and concise."
        )

        user_msg = f'RESEARCH QUERY: {query}\n\nSPECIALIST ANALYSES:{specialist_context}\n\nSynthesize into an executive briefing:'

        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg},
        ]

        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'reasoning'})
        event_q.put({'type': 'agent_thinking', 'agent': aid,
                     'text': 'Synthesising all specialist reports into executive briefing...'})

        full_response = _llm_call(messages, model, api_key, max_tokens=3072)

        # Stream in chunks
        chunk_size = max(1, len(full_response) // 6)
        for i in range(0, len(full_response), chunk_size):
            chunk = full_response[i:i+chunk_size]
            event_q.put({'type': 'agent_chunk', 'agent': aid, 'text': chunk})
            time.sleep(0.06)

        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'done'})
        event_q.put({'type': 'agent_result', 'agent': aid, 'text': full_response})

    except Exception as e:
        event_q.put({'type': 'agent_status', 'agent': aid, 'status': 'error'})
        event_q.put({'type': 'agent_error', 'agent': aid, 'message': str(e)})


def _stream_sse(wfile, event):
    """Write one SSE event to the response stream."""
    msg = f'data: {json.dumps(event)}\n\n'
    wfile.write(msg.encode())
    wfile.flush()


def run_swarm(wfile, query, model, api_key, brave_key):
    """Orchestrate the multi-agent swarm with SSE streaming.

    Flow:
    1. Announce agents
    2. Run 3 specialists in parallel (Market, Financial, Risk)
    3. Wait for all to complete
    4. Run Synthesis Lead with all specialist results
    5. Send done event
    """
    import concurrent.futures

    # Announce
    _stream_sse(wfile, {'type': 'swarm_start', 'query': query, 'agents': [
        {'id': a['id'], 'name': a['name'], 'icon': a['icon']} for a in SWARM_AGENTS
    ]})

    specialists = [a for a in SWARM_AGENTS if a['id'] != 'synthesis']
    event_q = _queue.Queue()
    agent_results = {}
    all_sources = []  # collected from all specialists for the final briefing

    # Run 3 specialists in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for i, agent in enumerate(specialists):
            future = executor.submit(
                _agent_worker, agent, query, model, api_key, brave_key,
                event_q, i, len(specialists), all_sources
            )
            futures[future] = agent['id']

        # Drain the event queue while agents are running
        done_count = 0
        total_specialists = len(specialists)

        while done_count < total_specialists:
            try:
                event = event_q.get(timeout=120)
            except _queue.Empty:
                _stream_sse(wfile, {'type': 'error', 'message': 'Agent timeout'})
                break

            # Check if this is a completion signal
            if event.get('type') == 'agent_result':
                aid = event.get('agent')
                agent_results[aid] = event.get('text', '')

            if event.get('type') == 'agent_status' and event.get('status') == 'done':
                done_count += 1
                event['total_done'] = done_count
                event['total'] = total_specialists

            # Check if this is an error
            if event.get('type') == 'agent_status' and event.get('status') == 'error':
                done_count += 1  # count errors as done too

            _stream_sse(wfile, event)

        # Wait for all threads to finish
        concurrent.futures.wait(futures.keys(), timeout=5)

    # Phase 2: Synthesis
    _stream_sse(wfile, {'type': 'phase', 'phase': 'synthesis', 'message': 'All specialists complete — Synthesis Lead is combining findings...'})
    time.sleep(0.3)

    synth_q = _queue.Queue()
    _synthesis_worker(query, model, api_key, agent_results, synth_q)

    # Drain synthesis events
    while True:
        try:
            event = synth_q.get(timeout=60)
            if event.get('type') == 'agent_result':
                agent_results['synthesis'] = event.get('text', '')
            _stream_sse(wfile, event)
            if event.get('type') == 'agent_status' and event.get('status') in ('done', 'error'):
                break
        except _queue.Empty:
            _stream_sse(wfile, {'type': 'error', 'message': 'Synthesis timeout'})
            break

    # Deduplicate sources by URL and send with the completion event
    seen_urls = set()
    unique_sources = []
    for s in all_sources:
        if s['url'] not in seen_urls:
            seen_urls.add(s['url'])
            unique_sources.append(s)

    # Send just a signal (not the full results — they're already streamed via chunks)
    _stream_sse(wfile, {'type': 'swarm_complete', 'sources': unique_sources})


class DemoHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/auth/login':
            self.handle_auth_login()
        elif self.path == '/api/auth/logout':
            self.handle_auth_logout()
        elif self.path == '/api/chat/completions':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_proxy()
        elif self.path == '/api/swarm':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_swarm()
        elif self.path == '/api/generate-image':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_generate_image()
        elif self.path == '/api/onboarding/employee':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_save_employee()
        elif self.path.startswith('/api/sim/'):
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_sim_api()
        elif self.path.startswith('/api/lg/'):
            # Public telemetry endpoints for Grafana — no auth required
            if self.path.split('?')[0] in ('/api/lg/grafana/telemetry', '/api/lg/grafana/line-overview'):
                self.handle_lineguard_grafana()
            elif not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_lineguard_api()
        elif self.path.startswith('/api/quant/'):
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            import quant_handler as qh
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            qh.handle_post(self, self.path, body)
        else:
            self.send_error(404)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/api/auth/check':
            self.handle_auth_check()
        elif path == '/api/onboarding/employees':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_list_employees()
        elif path == '/api/generate-icon':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_generate_icon()
        elif path.startswith('/api/search'):
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_search()
        elif path == '/api/models':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_proxy_get()
        elif path.startswith('/icons/') and path.endswith('.png'):
            self.serve_icon(path)
        elif path == '/chart.min.js':
            self.serve_static(path)
        elif path.startswith('/api/lg/'):
            # Public telemetry endpoints for Grafana — no auth required
            if path in ('/api/lg/grafana/telemetry', '/api/lg/grafana/line-overview'):
                self.handle_lineguard_grafana()
            elif not self.get_authenticated_user():
                self.send_auth_error()
                return
            self.handle_lineguard_api()
        elif path.startswith('/api/quant/') and path != '/api/quant/run':
            if not self.get_authenticated_user():
                self.send_auth_error()
                return
            import quant_handler as qh
            params = parse_qs(urlparse(self.path).query)
            qh.handle_get(self, path, params)
        elif path in ('/cyber-timeline.js', '/cyber-attack-sim.js', '/cyber-forensic.js', '/autonomous.js', '/worker.js', '/onboarding.js', '/lineguard.js', '/ab-compare.js'):
            self.serve_static(path)
        elif path in ('/', '/index.html'):
            self.serve_index()
        elif path == '/manual.html':
            self.serve_manual()
        elif path == '/gmq.html':
            self.serve_gmq()
        elif path == '/quant-arena.html':
            self.serve_quant_arena()
        else:
            super().do_GET()

    def serve_icon(self, path):
        """Serve an icon image from the icons directory."""
        filename = path.split('/')[-1]
        icon_path = ICON_DIR / filename
        if icon_path.exists():
            data = icon_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Icon not found"}')

    def serve_quant_arena(self):
        """Serve quant-arena.html as text/html (not octet-stream)."""
        qa_path = Path(__file__).parent / 'quant-arena.html'
        if qa_path.exists():
            data = qa_path.read_bytes()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Disposition', 'inline')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Quant Arena not found"}')

    def serve_static(self, path):
        """Serve a static file from the project directory."""
        file_path = Path(__file__).parent / path.lstrip('/')
        if file_path.exists():
            data = file_path.read_bytes()
            content_type = 'application/javascript' if path.endswith('.js') else 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def serve_index(self):
        """Serve index.html with API key injected for local use."""
        index_path = Path(__file__).parent / 'index.html'
        html = index_path.read_text()
        import re
        # On localhost, the server proxy handles auth — just give JS a truthy key
        # and fix the broken line where patch redacted 'val' to '***'
        html = re.sub(
            r'let API_KEY=.*?// server proxy handles auth',
            'let API_KEY="server-proxied";  // auth handled by localhost proxy',
            html
        )
        # Fix API_KEY assignment: replace broken *** with val
        html = re.sub(
            r'API_KEY=\*{3}\s+localStorage',
            'API_KEY=val; localStorage',
            html
        )
        data = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_manual(self):
        """Serve manual.html (no auth required — it's documentation)."""
        manual_path = Path(__file__).parent / 'manual.html'
        if manual_path.exists():
            data = manual_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Manual not found"}')

    def serve_gmq(self):
        """Serve gmq.html — admin only (neil.bowden@dell.com)."""
        user = self.get_authenticated_user()
        # Also accept token via query param (for iframe embeds)
        if not user:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            token = params.get('token', [''])[0]
            if token:
                try:
                    conn = _get_db()
                    row = conn.execute(
                        """SELECT u.id, u.email, s.expires_at
                           FROM sessions s JOIN users u ON s.user_id = u.id
                           WHERE s.token = ?""",
                        (token,)
                    ).fetchone()
                    conn.close()
                    if row:
                        expires = row['expires_at']
                        if expires and expires > datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'):
                            user = {'id': row['id'], 'email': row['email']}
                except Exception as e:
                    print(f'GMQ query-token auth error: {e}')
        if not user:
            self.send_json_response(401, {'error': 'Authentication required'})
            return
        admin_emails = {'neil.bowden@dell.com', 'j.bowden@waveguideltd.com'}
        if user.get('email') not in admin_emails:
            self.send_json_response(403, {'error': 'Access denied'})
            return
        gmq_path = Path(__file__).parent / 'gmq.html'
        if gmq_path.exists():
            data = gmq_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"GMQ demo not found"}')

    # ─── AUTH METHODS ───

    def get_authenticated_user(self):
        """Check if request has valid session token. Returns user dict or None."""
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            try:
                conn = _get_db()
                row = conn.execute(
                    """SELECT u.id, u.email, s.expires_at
                       FROM sessions s JOIN users u ON s.user_id = u.id
                       WHERE s.token = ?""",
                    (token,)
                ).fetchone()
                conn.close()
                if row:
                    expires = row['expires_at']
                    if expires and expires > datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'):
                        return {'id': row['id'], 'email': row['email']}
            except Exception as e:
                print(f'Auth check error: {e}')
        return None

    def handle_auth_login(self):
        """Handle POST /api/auth/login"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body)
            email = data.get('email', '').strip()
            password = data.get('password', '')
        except:
            self.send_json_response(400, {'success': False, 'error': 'Invalid request body'})
            return

        if not email or not password:
            self._log_login(None, email, False)
            self.send_json_response(400, {'success': False, 'error': 'Email and password required'})
            return

        try:
            conn = _get_db()
            user = conn.execute('SELECT id, email, password_hash, salt FROM users WHERE email = ?', (email,)).fetchone()
            if not user:
                conn.close()
                self._log_login(None, email, False)
                self.send_json_response(401, {'success': False, 'error': 'Invalid credentials'})
                return

            # Hash password with stored salt and compare
            password_hash = hashlib.sha256((user['salt'] + password).encode()).hexdigest()
            if password_hash != user['password_hash']:
                conn.close()
                self._log_login(user['id'], email, False)
                self.send_json_response(401, {'success': False, 'error': 'Invalid credentials'})
                return

            # Generate session token
            token = secrets.token_hex(32)
            expires_at = (datetime.utcnow() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)',
                (token, user['id'], expires_at)
            )
            conn.commit()
            conn.close()

            self._log_login(user['id'], email, True)
            self.send_json_response(200, {'success': True, 'token': token})
        except Exception as e:
            print(f'Login error: {e}')
            self.send_json_response(500, {'success': False, 'error': 'Server error'})

    def handle_auth_logout(self):
        """Handle POST /api/auth/logout"""
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            try:
                conn = _get_db()
                conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f'Logout error: {e}')
        self.send_json_response(200, {'success': True})

    def handle_auth_check(self):
        """Handle GET /api/auth/check"""
        user = self.get_authenticated_user()
        if user:
            self.send_json_response(200, {'authenticated': True, 'email': user['email']})
        else:
            self.send_json_response(200, {'authenticated': False})

    def send_auth_error(self):
        """Send 401 authentication required response."""
        self.send_json_response(401, {'error': 'Authentication required'})

    def _log_login(self, user_id, email, success):
        """Log a login attempt to the login_log table."""
        try:
            ip = self.client_address[0] if self.client_address else 'unknown'
            # Check for forwarded IP (behind nginx proxy on Hetzner)
            fwd = self.headers.get('X-Forwarded-For', '')
            if fwd:
                ip = fwd.split(',')[0].strip()
            ua = self.headers.get('User-Agent', 'unknown')
            conn = _get_db()
            conn.execute(
                'INSERT INTO login_log (user_id, email, success, ip_address, user_agent) VALUES (?, ?, ?, ?, ?)',
                (user_id, email, 1 if success else 0, ip, ua)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'Login log error: {e}')

    def send_json_response(self, code, data):
        """Send a JSON response with CORS headers."""
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ─── ICON GENERATION ───

    def handle_generate_icon(self):
        """Handle GET /api/generate-icon?demo=NAME"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        demo = params.get('demo', [''])[0]

        if demo not in ICON_PROMPTS:
            self.send_json_response(400, {'error': f'Invalid demo name. Valid: {", ".join(ICON_PROMPTS.keys())}'})
            return

        icon_path = ICON_DIR / f'{demo}.png'
        if icon_path.exists():
            self.send_json_response(200, {'status': 'exists', 'url': f'/icons/{demo}.png'})
            return

        # Start generation in background thread
        t = threading.Thread(target=generate_icon_file, args=(demo,), daemon=True)
        t.start()
        self.send_json_response(202, {'status': 'generating', 'demo': demo})

    def handle_proxy(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''

        # Inject API key if not present in request
        try:
            req_data = json.loads(body)
        except:
            req_data = {}

        # Route to Anthropic if model starts with "anthropic/"
        model = req_data.get('model', '')
        if model.startswith('anthropic/'):
            self._handle_anthropic_proxy(req_data)
            return

        # Use server-side key if not present in request
        if API_KEY and 'model' in req_data:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {API_KEY}'
            }
        else:
            # Forward client's auth header
            auth = self.headers.get('Authorization', '')
            headers = {
                'Content-Type': 'application/json',
                'Authorization': auth
            }

        is_stream = req_data.get('stream', False)
        target_url = f'{API_BASE}/chat/completions'

        try:
            req = urllib.request.Request(target_url, data=body, headers=headers, method='POST')
            resp = urllib.request.urlopen(req, timeout=120)

            if is_stream:
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                # Stream the response
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            else:
                data = resp.read()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)

        except urllib.error.HTTPError as e:
            error_body = e.read()
            self.send_response(e.code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(error_body)

        except Exception as e:
            self.send_response(502)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def handle_search(self):
        """Proxy Brave Search API requests."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        query = params.get('q', [''])[0]
        count = min(int(params.get('count', ['8'])[0]), 20)

        if not query:
            self.send_response(400)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing q parameter'}).encode())
            return

        if not BRAVE_KEY:
            self.send_response(503)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'No Brave API key configured'}).encode())
            return

        target = f'https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={count}'
        try:
            req = urllib.request.Request(target, headers={
                'Accept': 'application/json',
                'X-Subscription-Token': BRAVE_KEY
            })
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_anthropic_proxy(self, req_data):
        """Convert OpenAI chat completions format to Anthropic Messages API format."""
        model = req_data['model'].replace('anthropic/', '')
        messages = req_data.get('messages', [])
        max_tokens = req_data.get('max_tokens', 4096)
        stream = req_data.get('stream', False)

        # Split system message from conversation
        system_content = ''
        conv_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_content += msg['content'] + '\n'
            else:
                conv_messages.append({'role': msg['role'], 'content': msg['content']})

        anthropic_req = {
            'model': model,
            'max_tokens': max_tokens,
            'messages': conv_messages,
            'stream': stream,
        }
        if system_content.strip():
            anthropic_req['system'] = system_content.strip()

        body = json.dumps(anthropic_req).encode()
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
        }

        try:
            req = urllib.request.Request(
                f'{ANTHROPIC_BASE}/messages',
                data=body,
                headers=headers,
                method='POST'
            )
            resp = urllib.request.urlopen(req, timeout=120)

            if stream:
                # Convert Anthropic SSE stream to OpenAI SSE format
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()

                buffer = ''
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        # Send [DONE]
                        self.wfile.write(b'data: [DONE]\n\n')
                        self.wfile.flush()
                        break
                    buffer += chunk.decode()
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
                                    # Wrap in OpenAI format
                                    openai_chunk = {
                                        'choices': [{'delta': {'content': text}, 'index': 0}]
                                    }
                                    self.wfile.write(f'data: {json.dumps(openai_chunk)}\n\n'.encode())
                                    self.wfile.flush()
                        except (json.JSONDecodeError, KeyError):
                            pass
            else:
                # Non-streaming: convert Anthropic response to OpenAI format
                data = json.loads(resp.read())
                text = ''
                for block in data.get('content', []):
                    if block.get('type') == 'text':
                        text += block.get('text', '')

                openai_response = {
                    'choices': [{
                        'message': {'role': 'assistant', 'content': text},
                        'finish_reason': 'stop',
                        'index': 0
                    }],
                    'usage': {
                        'prompt_tokens': data.get('usage', {}).get('input_tokens', 0),
                        'completion_tokens': data.get('usage', {}).get('output_tokens', 0),
                        'total_tokens': data.get('usage', {}).get('input_tokens', 0) + data.get('usage', {}).get('output_tokens', 0),
                    }
                }
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(openai_response).encode())

        except urllib.error.HTTPError as e:
            error_body = e.read()
            self.send_response(e.code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(error_body)
        except Exception as e:
            self.send_response(502)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def handle_proxy_get(self):
        auth = self.headers.get('Authorization', f'Bearer {API_KEY}' if API_KEY else '')
        target_url = f'{API_BASE}/models'
        try:
            req = urllib.request.Request(target_url, headers={'Authorization': auth})
            resp = urllib.request.urlopen(req, timeout=30)
            data = resp.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(e.read())

    # ─── MULTI-AGENT RESEARCH SWARM ───

    def handle_swarm(self):
        """Handle POST /api/swarm — multi-agent research with SSE streaming.

        Spawns specialist agents (Market Researcher, Financial Analyst,
        Risk/Regulatory, Synthesis Lead) that run in parallel threads.
        Each agent performs web searches + LLM reasoning, streaming events
        back to the browser via Server-Sent Events.
        """
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            req_data = json.loads(body)
            query = req_data.get('query', '').strip()
            model = req_data.get('model', 'deepseek/deepseek-v4-flash-0731')
        except Exception:
            self.send_json_response(400, {'error': 'Invalid JSON body'})
            return

        if not query:
            self.send_json_response(400, {'error': 'query is required'})
            return

        # SSE headers
        self.send_response(200)
        self.send_cors_headers()
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.end_headers()

        # Run the swarm — blocks until all agents complete
        try:
            run_swarm(self.wfile, query, model, API_KEY, BRAVE_KEY)
        except Exception as e:
            self._sse_send({'type': 'error', 'message': str(e)})
        finally:
            try:
                self._sse_send({'type': 'done'})
            except Exception:
                pass

    def _sse_send(self, data):
        """Send a single SSE event."""
        msg = f'data: {json.dumps(data)}\n\n'
        self.wfile.write(msg.encode())
        self.wfile.flush()

    def handle_generate_image(self):
        """Handle POST /api/generate-image — proxy to PiAPI gpt-image-1."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body)
            prompt = data.get('prompt', '').strip()
            style = data.get('style', 'Photorealistic')
            size = data.get('size', '1024x1024')
        except Exception:
            self.send_json_response(400, {'success': False, 'error': 'Invalid request body'})
            return

        if not prompt:
            self.send_json_response(400, {'success': False, 'error': 'Prompt is required'})
            return

        full_prompt = f"A {style} image of: {prompt}. High quality, detailed."

        try:
            req_data = json.dumps({
                'model': 'gpt-image-1',
                'prompt': full_prompt,
                'size': size,
                'n': 1,
                'response_format': 'b64_json'
            }).encode()

            req = urllib.request.Request(
                'https://api.piapi.ai/v1/images/generations',
                data=req_data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {PIAPI_KEY}',
                    'User-Agent': 'AI-Demos-Portal/1.0'
                },
                method='POST'
            )

            resp = urllib.request.urlopen(req, timeout=120)
            resp_data = json.loads(resp.read())

            # Extract base64 image and revised prompt
            image_b64 = None
            revised_prompt = ''
            if 'data' in resp_data and len(resp_data['data']) > 0:
                item = resp_data['data'][0]
                image_b64 = item.get('b64_json', '')
                revised_prompt = item.get('revised_prompt', full_prompt)

            if image_b64:
                self.send_json_response(200, {
                    'success': True,
                    'image': image_b64,
                    'revised_prompt': revised_prompt
                })
            else:
                self.send_json_response(500, {
                    'success': False,
                    'error': 'No image data in response'
                })

        except urllib.error.HTTPError as e:
            error_body = e.read()
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get('error', {}).get('message', str(error_json))
            except Exception:
                error_msg = error_body.decode()[:200]
            self.send_json_response(e.code, {'success': False, 'error': error_msg})

        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── ONBOARDING EMPLOYEE ENDPOINTS ──
    def handle_save_employee(self):
        """POST /api/onboarding/employee — save a new employee to the database."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body)
        except Exception:
            self.send_json_response(400, {'success': False, 'error': 'Invalid JSON body'})
            return

        name = data.get('name', '').strip()
        if not name:
            self.send_json_response(400, {'success': False, 'error': 'Name is required'})
            return

        try:
            conn = sqlite3.connect(str(AUTH_DB_PATH))
            conn.execute(
                '''INSERT INTO onboarding_employees
                   (name, email, role, department, start_date, location, manager, agent_tasks, welcome_packet, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    name,
                    data.get('email', ''),
                    data.get('role', ''),
                    data.get('department', ''),
                    data.get('startDate', ''),
                    data.get('location', ''),
                    data.get('manager', ''),
                    json.dumps(data.get('agentTasks', [])),
                    data.get('welcomePacket', ''),
                    data.get('status', 'onboarded'),
                )
            )
            emp_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
            conn.close()
            self.send_json_response(200, {'success': True, 'id': emp_id})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_list_employees(self):
        """GET /api/onboarding/employees — list all onboarded employees."""
        try:
            conn = sqlite3.connect(str(AUTH_DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT id, name, email, role, department, start_date, location, manager, status, created_at FROM onboarding_employees ORDER BY created_at DESC'
            ).fetchall()
            employees = [dict(r) for r in rows]
            conn.close()
            self.send_json_response(200, {'success': True, 'employees': employees, 'count': len(employees)})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')

    # ── SIMULATED SYSTEM APIs (for onboarding agent tools) ──
    def handle_sim_api(self):
        """POST /api/sim/<system> — simulated IT/HR system calls for agent tools."""
        path = self.path.split('?')[0]
        system = path.replace('/api/sim/', '')

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        # In-memory state for the session (persists during server lifetime)
        if not hasattr(self.server, '_sim_state'):
            self.server._sim_state = {
                'emails': set(), 'slack_channels': set(), 'github_users': set(),
                'inventory': {'laptop': 3, 'monitor': 5, 'headset': 10, 'phone': 4},
                'contracts': {}, 'approvals': {}, 'vpn_profiles': set(),
                'training_assigned': set(), 'assets': {}, 'accounts': {},
            }
        st = self.server._sim_state

        def make_email(name):
            parts = name.lower().replace("'", "").replace("-", "").split()
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}@company.com"
            return f"{parts[0]}@company.com" if parts else "employee@company.com"

        results = {
            'email': lambda: self._sim_email(st, data, make_email),
            'slack': lambda: self._sim_slack(st, data),
            'github': lambda: self._sim_github(st, data),
            'inventory': lambda: self._sim_inventory(st, data),
            'contract': lambda: self._sim_contract(st, data),
            'approval': lambda: self._sim_approval(st, data),
            'vpn': lambda: self._sim_vpn(st, data),
            'training': lambda: self._sim_training(st, data),
            'calendar': lambda: self._sim_calendar(st, data),
            'asset': lambda: self._sim_asset(st, data),
        }

        handler = results.get(system)
        if handler:
            try:
                result = handler()
                self.send_json_response(200, {'success': True, 'system': system, 'result': result})
            except Exception as e:
                self.send_json_response(200, {'success': False, 'system': system, 'error': str(e)})
        else:
            self.send_json_response(404, {'error': f'Unknown system: {system}'})

    def _sim_email(self, st, data, make_email):
        name = data.get('name', 'employee')
        email = data.get('email') or make_email(name)
        if email in st['emails']:
            # Collision — generate variant
            base = email.split('@')[0]
            domain = email.split('@')[1] if '@' in email else 'company.com'
            email = f"{base}.{random.randint(100,999)}@{domain}"
            st['emails'].add(email)
            return {'email': email, 'note': 'Email collision detected, generated variant', 'status': 'created_with_variant'}
        st['emails'].add(email)
        return {'email': email, 'status': 'created', 'mailbox': f'mailbox-{random.randint(1000,9999)}'}

    def _sim_slack(self, st, data):
        action = data.get('action', 'invite')
        email = data.get('email', '')
        channel = data.get('channel', 'general')
        if action == 'invite':
            if not email:
                return {'error': 'email required for invite'}
            return {'user': email, 'channel': channel, 'status': 'invited', 'workspace': 'company.slack.com'}
        elif action == 'create_channel':
            if channel in st['slack_channels']:
                return {'channel': channel, 'status': 'already_exists'}
            st['slack_channels'].add(channel)
            return {'channel': channel, 'status': 'created'}
        return {'error': f'unknown action: {action}'}

    def _sim_github(self, st, data):
        username = data.get('username', data.get('email', 'user').split('@')[0])
        org = data.get('org', 'company')
        team = data.get('team', 'developers')
        if username in st['github_users']:
            return {'username': username, 'status': 'already_member', 'org': org}
        st['github_users'].add(username)
        return {'username': username, 'org': org, 'team': team, 'status': 'invited', 'permissions': 'write'}

    def _sim_inventory(self, st, data):
        item = data.get('item', 'laptop')
        qty = st['inventory'].get(item, 0)
        if qty <= 0:
            return {'item': item, 'status': 'out_of_stock', 'note': 'Procurement required — estimated 5-7 business days'}
        st['inventory'][item] = qty - 1
        asset_tag = f"DELL-{random.randint(1000,9999)}"
        st['assets'][asset_tag] = {'item': item, 'assigned_to': data.get('name', 'employee')}
        return {'item': item, 'status': 'assigned', 'asset_tag': asset_tag, 'remaining_stock': qty - 1}

    def _sim_contract(self, st, data):
        contract_type = data.get('type', 'employment')
        name = data.get('name', 'employee')
        contract_id = f"CTR-{random.randint(10000,99999)}"
        st['contracts'][contract_id] = {'type': contract_type, 'name': name, 'status': 'sent_for_signature'}
        return {'contract_id': contract_id, 'type': contract_type, 'status': 'sent_for_signature', 'recipient': name}

    def _sim_approval(self, st, data):
        approver = data.get('approver', 'IT')
        request_type = data.get('type', 'account_provisioning')
        approval_id = f"APR-{random.randint(10000,99999)}"
        # Simulate: 80% auto-approve, 20% need manual review
        auto = random.random() < 0.8
        st['approvals'][approval_id] = {'approver': approver, 'type': request_type, 'status': 'approved' if auto else 'pending_review'}
        return {'approval_id': approval_id, 'approver': approver, 'status': 'approved' if auto else 'pending_review', 'type': request_type}

    def _sim_vpn(self, st, data):
        email = data.get('email', 'user@company.com')
        profile_name = email.split('@')[0] + '_vpn'
        if profile_name in st['vpn_profiles']:
            return {'profile': profile_name, 'status': 'already_exists'}
        st['vpn_profiles'].add(profile_name)
        return {'profile': profile_name, 'status': 'configured', 'protocol': 'WireGuard', 'server': 'vpn.company.com'}

    def _sim_training(self, st, data):
        name = data.get('name', 'employee')
        course = data.get('course', 'GDPR Compliance')
        key = f"{name}:{course}"
        if key in st['training_assigned']:
            return {'course': course, 'status': 'already_assigned'}
        st['training_assigned'].add(key)
        return {'course': course, 'status': 'assigned', 'due_date': '30 days', 'platform': 'Company LMS'}

    def _sim_calendar(self, st, data):
        name = data.get('name', 'employee')
        manager = data.get('manager', 'Manager')
        events = [
            {'day': 'Day 1', 'time': '09:30', 'event': f'Welcome meeting with {manager}'},
            {'day': 'Day 1', 'time': '14:00', 'event': 'IT setup & equipment handover'},
            {'day': 'Day 2', 'time': '10:00', 'event': 'Team introduction & desk tour'},
            {'day': 'Day 3', 'time': '11:00', 'event': '1:1 with ' + manager},
            {'day': 'Day 4', 'time': '09:00', 'event': 'Security & compliance training'},
            {'day': 'Day 5', 'time': '15:00', 'event': 'Week 1 review with ' + manager},
        ]
        return {'events': events, 'calendar': f'{name.lower().replace(" ", ".")}@company.com', 'status': 'configured'}

    def _sim_asset(self, st, data):
        action = data.get('action', 'register')
        if action == 'register':
            asset_tag = data.get('asset_tag', f"DELL-{random.randint(1000,9999)}")
            name = data.get('name', 'employee')
            st['assets'][asset_tag] = {'assigned_to': name, 'item': data.get('item', 'laptop')}
            return {'asset_tag': asset_tag, 'assigned_to': name, 'status': 'registered'}
        elif action == 'list':
            return {'assets': [{'tag': k, **v} for k, v in st['assets'].items()]}
        return {'error': f'unknown action: {action}'}

    def handle_lineguard_api(self):
        """Handle LineGuard AI API endpoints — telemetry, assets, maintenance, etc."""
        import lineguard_data as lg
        path = self.path.split('?')[0]
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        # ─── GET endpoints ───
        if self.command == 'GET':
            if path == '/api/lg/assets':
                self.send_json_response(200, {'assets': lg.ASSETS, 'metrics': lg.ASSET_METRICS, 'labels': lg.METRIC_LABELS})
            elif path == '/api/lg/telemetry/snapshot':
                asset_id = params.get('asset_id', [''])[0]
                if asset_id in lg.ASSETS:
                    self.send_json_response(200, lg.get_asset_snapshot(asset_id))
                else:
                    self.send_json_response(404, {'error': 'Asset not found'})
            elif path == '/api/lg/telemetry/series':
                asset_id = params.get('asset_id', [''])[0]
                metric = params.get('metric', [''])[0]
                points = int(params.get('points', ['60'])[0])
                if asset_id in lg.ASSETS and metric in lg.ASSETS[asset_id].get('baselines', {}):
                    series = lg.generate_series(asset_id, metric, points)
                    self.send_json_response(200, {'series': series})
                else:
                    self.send_json_response(404, {'error': 'Asset or metric not found'})
            elif path == '/api/lg/anomalies':
                self.send_json_response(200, {'anomalies': lg.list_active_anomalies(lg.SITE_ID)})
            elif path == '/api/lg/maintenance/history':
                asset_id = params.get('asset_id', [''])[0]
                query = params.get('q', [''])[0]
                self.send_json_response(200, {'records': lg.search_maintenance_history(asset_id, query)})
            elif path == '/api/lg/documents/search':
                asset_id = params.get('asset_id', [''])[0]
                query = params.get('q', [''])[0]
                self.send_json_response(200, {'documents': lg.search_technical_documents(asset_id, query)})
            elif path == '/api/lg/schedule':
                line_id = params.get('line_id', [lg.LINE_ID])[0]
                self.send_json_response(200, lg.get_production_schedule(line_id))
            elif path == '/api/lg/inventory':
                part_number = params.get('part_number', [None])[0]
                self.send_json_response(200, {'inventory': lg.get_inventory(part_number)})
            elif path == '/api/lg/technicians':
                skill = params.get('skill', [None])[0]
                self.send_json_response(200, {'technicians': lg.get_technician_availability(skill)})
            elif path == '/api/lg/observations':
                asset_id = params.get('asset_id', [''])[0]
                self.send_json_response(200, {'observations': lg.get_operator_observations(asset_id)})
            elif path == '/api/lg/downtime-impact':
                asset_id = params.get('asset_id', [''])[0]
                duration = int(params.get('duration', ['55'])[0])
                self.send_json_response(200, lg.estimate_downtime_impact(asset_id, duration))
            elif path == '/api/lg/work-orders':
                self.send_json_response(200, {'work_orders': lg.get_work_orders()})
            elif path == '/api/lg/reset':
                lg.reset_state()
                self.send_json_response(200, {'success': True, 'message': 'LineGuard state reset'})
            else:
                self.send_json_response(404, {'error': f'Unknown endpoint: {path}'})

        # ─── POST endpoints ───
        elif self.command == 'POST':
            if path == '/api/lg/work-order/draft':
                wo = lg.draft_work_order(data)
                self.send_json_response(200, {'success': True, 'work_order': wo})
            elif path == '/api/lg/approval/request':
                apr = lg.send_approval_request(data)
                self.send_json_response(200, {'success': True, 'approval': apr})
            elif path == '/api/lg/observation/add':
                obs = lg.add_operator_observation(data.get('asset_id', 'PRESS-02'), data.get('observation', ''), data.get('operator', 'Demo Presenter'))
                self.send_json_response(200, {'success': True, 'observation': obs})
            elif path == '/api/lg/event/delay-part':
                lg.delay_part(data.get('part_number', 'BR-500-A'))
                self.send_json_response(200, {'success': True, 'message': f"Part {data.get('part_number', 'BR-500-A')} marked as delayed"})
            elif path == '/api/lg/event/reset':
                lg.reset_state()
                self.send_json_response(200, {'success': True, 'message': 'All events reset'})
            else:
                self.send_json_response(404, {'error': f'Unknown endpoint: {path}'})
        else:
            self.send_json_response(405, {'error': 'Method not allowed'})

    def handle_lineguard_grafana(self):
        """Public unauthenticated telemetry endpoint for Grafana Infinity datasource."""
        import lineguard_data as lg
        path = self.path.split('?')[0]
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if path == '/api/lg/grafana/telemetry':
            # Returns flat array of all asset readings — perfect for Grafana timeseries
            readings = []
            for asset_id in lg.ASSETS:
                snap = lg.get_asset_snapshot(asset_id)
                asset = lg.ASSETS[asset_id]
                for metric, r in snap['metrics'].items():
                    label = lg.METRIC_LABELS.get(metric, metric)
                    limits = asset['operating_limits'].get(metric, {})
                    warn = limits.get('warn', r.get('baseline', 0))
                    crit = limits.get('crit', r.get('baseline', 0) * 1.5)
                    readings.append({
                        'time': int(r['timestamp'] * 1000),  # Grafana expects ms
                        'asset_id': asset_id,
                        'asset_name': asset['name'],
                        'asset_type': asset['type'],
                        'criticality': asset['criticality'],
                        'location': asset['location'],
                        'metric': metric,
                        'metric_label': label,
                        'value': r['value'],
                        'unit': r.get('unit', ''),
                        'baseline': r.get('baseline', 0),
                        'warn_threshold': warn,
                        'crit_threshold': crit,
                        'status': r['status'],
                        'overall_status': snap['overall_status'],
                        'anomaly_count': snap['anomaly_count'],
                    })
            self.send_json_response(200, readings)

        elif path == '/api/lg/grafana/line-overview':
            # Returns line summary for stat panels
            overview = {
                'line_id': lg.LINE_ID,
                'site_id': lg.SITE_ID,
                'assets': [],
                'active_anomalies': len(lg.list_active_anomalies(lg.SITE_ID)),
                'timestamp': int(time.time() * 1000),
            }
            for asset_id in lg.ASSETS:
                snap = lg.get_asset_snapshot(asset_id)
                asset = lg.ASSETS[asset_id]
                overview['assets'].append({
                    'asset_id': asset_id,
                    'name': asset['name'],
                    'type': asset['type'],
                    'criticality': asset['criticality'],
                    'status': snap['overall_status'],
                    'anomaly_count': snap['anomaly_count'],
                    'risk_score': 75 if snap['overall_status'] == 'critical' else 40 if snap['overall_status'] == 'warning' else 10,
                })
            self.send_json_response(200, overview)
        else:
            self.send_json_response(404, {'error': 'Unknown grafana endpoint'})

    def log_message(self, format, *args):
        # Quieter logging — only show API calls and errors
        msg = format % args
        if '/api/' in msg or '200' not in msg:
            super().log_message(format, *args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AI Demos Server')
    parser.add_argument('--port', type=int, default=8888)
    parser.add_argument('--api-key', type=str, default='', help='Tensorx API key (or set TENSORX_API_KEY env var)')
    args = parser.parse_args()

    if args.api_key:
        API_KEY = args.api_key

    if not API_KEY:
        # Try loading from .env
        env_path = Path.home() / '.hermes' / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if (line.startswith('TENSORX_API_KEY=') or line.startswith('TENSORIX_API_KEY=')) and '***' not in line:
                    API_KEY = line.split('=', 1)[1]
                    break

    if API_KEY:
        print(f'✓ API key loaded ({len(API_KEY)} chars)')
    else:
        print('⚠ No API key — users must enter their own key in the UI')

    # Initialize auth database
    init_db()
    cleanup_sessions()

    # Create icons directory
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(ICON_DIR.glob('*.png'))
    print(f'✓ Icons directory ready ({len(existing)} icons cached)')

    # Start periodic session cleanup
    session_cleanup_timer()

    # Initialize Quant Arena handler
    try:
        import quant_handler as qh
        qh.init(API_KEY, API_BASE, ANTHROPIC_API_KEY)
        print('✓ Quant Arena handler initialized')
    except ImportError:
        print('⚠ Quant Arena handler not found — quant routes disabled')

    print(f'⚡ AI Demos running at http://localhost:{args.port}')
    print(f'   Press Ctrl+C to stop')

    server = http.server.ThreadingHTTPServer(('0.0.0.0', args.port), DemoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
