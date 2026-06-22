#!/usr/bin/env python3
"""
Local AI Demos server — serves the portal and proxies API calls to Tensorix.
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

API_BASE = 'https://api.tensorix.ai/v1'
API_KEY = os.environ.get('TENSORIX_API_KEY', '')

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
        if self.path == '/api/models':
            self.handle_proxy_get()
        else:
            super().do_GET()

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
    parser.add_argument('--api-key', type=str, default='', help='Tensorix API key (or set TENSORIX_API_KEY env var)')
    args = parser.parse_args()

    if args.api_key:
        API_KEY = args.api_key

    if not API_KEY:
        # Try loading from .env
        env_path = Path.home() / '.hermes' / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('TENSORIX_API_KEY=') and '***' not in line:
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
