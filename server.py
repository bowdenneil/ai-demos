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
import urllib.request
import urllib.error
import argparse
from pathlib import Path

API_BASE = 'https://api.tensorx.ai/v1'
API_KEY = os.environ.get('TENSORX_API_KEY', '') or os.environ.get('TENSORIX_API_KEY', '') or 'sk-9ub...XReg'
BRAVE_KEY = os.environ.get('BRAVE_SEARCH_KEY', '') or 'BSAezzPy7F1dgfj5TSSTQRWve35pO8H'

class DemoHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/chat/completions':
            self.handle_proxy()
        else:
            self.send_error(404)

    def do_GET(self):
        path = self.path.split('?')[0]
        if self.path.startswith('/api/search'):
            self.handle_search()
        elif self.path == '/api/models':
            self.handle_proxy_get()
        elif path in ('/', '/index.html'):
            self.serve_index()
        else:
            super().do_GET()

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

    def handle_proxy(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''

        # Inject API key if not present in request
        try:
            req_data = json.loads(body)
        except:
            req_data = {}

        # Use server-side key if client didn't provide one
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
        from urllib.parse import urlparse, parse_qs
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

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

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

    print(f'⚡ AI Demos running at http://localhost:{args.port}')
    print(f'   Press Ctrl+C to stop')

    server = http.server.HTTPServer(('0.0.0.0', args.port), DemoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
