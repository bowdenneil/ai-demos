#!/usr/bin/env python3
"""
Guest Login Tracker — checks for new guest logins on the AI Demos portal.

Checks both local and remote (Hetzner) auth databases for guest@aidemos.com
login activity since the last check. Outputs a summary suitable for Hermes cron.

Usage:
    python3 guest_tracker.py              # check since last run
    python3 guest_tracker.py --all        # show all guest logins ever
    python3 guest_tracker.py --days 7    # last 7 days

State file: ~/.ai-demos/.last_tracker_run
Local DB:   ~/.ai-demos/auth.db
Remote DB:  SSH root@167.233.117.179:/home/ai-demos/.ai-demos/auth.db
"""
import sqlite3
import subprocess
import sys
import json
import argparse
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta

AUTH_DB = Path.home() / '.ai-demos' / 'auth.db'
REMOTE_HOST = 'root@167.233.117.179'
REMOTE_DB = '/home/ai-demos/.ai-demos/auth.db'
STATE_FILE = Path.home() / '.ai-demos' / '.last_tracker_run'
GUEST_EMAIL = 'guest@aidemos.com'


def get_last_run():
    """Get the timestamp of the last tracker run."""
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip()
    return None


def save_run(ts):
    """Save the current run timestamp."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(ts)


def query_local_db(since=None):
    """Query local auth.db for guest logins."""
    if not AUTH_DB.exists():
        return [], 'local DB not found'
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.row_factory = sqlite3.Row
        if since:
            rows = conn.execute(
                """SELECT email, success, ip_address, user_agent, created_at
                   FROM login_log
                   WHERE email = ? AND created_at > ?
                   ORDER BY created_at DESC""",
                (GUEST_EMAIL, since)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT email, success, ip_address, user_agent, created_at
                   FROM login_log
                   WHERE email = ?
                   ORDER BY created_at DESC""",
                (GUEST_EMAIL,)
            ).fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results, None
    except Exception as e:
        return [], str(e)


def query_remote_db(since=None):
    """Query remote (Hetzner) auth.db for guest logins via SSH."""
    # Download a copy of the remote DB to a temp file
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        result = subprocess.run(
            ['scp', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=no',
             f'{REMOTE_HOST}:{REMOTE_DB}', tmp.name],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return [], f'SCP failed: {result.stderr.strip()}'

        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row

        # Check if login_log table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='login_log'"
        ).fetchall()
        if not tables:
            # Fallback: use sessions table (pre-update deployments)
            if since:
                rows = conn.execute(
                    """SELECT u.email, 1 as success, NULL as ip_address,
                              'unknown' as user_agent, s.created_at
                       FROM sessions s JOIN users u ON s.user_id = u.id
                       WHERE u.email = ? AND s.created_at > ?
                       ORDER BY s.created_at DESC""",
                    (GUEST_EMAIL, since)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT u.email, 1 as success, NULL as ip_address,
                              'unknown' as user_agent, s.created_at
                       FROM sessions s JOIN users u ON s.user_id = u.id
                       WHERE u.email = ?
                       ORDER BY s.created_at DESC""",
                    (GUEST_EMAIL,)
                ).fetchall()
        else:
            if since:
                rows = conn.execute(
                    """SELECT email, success, ip_address, user_agent, created_at
                       FROM login_log
                       WHERE email = ? AND created_at > ?
                       ORDER BY created_at DESC""",
                    (GUEST_EMAIL, since)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT email, success, ip_address, user_agent, created_at
                       FROM login_log
                       WHERE email = ?
                       ORDER BY created_at DESC""",
                    (GUEST_EMAIL,)
                ).fetchall()

        results = [dict(r) for r in rows]
        conn.close()
        return results, None
    except subprocess.TimeoutExpired:
        return [], 'SSH timeout'
    except Exception as e:
        return [], str(e)
    finally:
        os.unlink(tmp.name)


def format_report(local_logins, remote_logins, since, errors):
    """Format the results into a readable report."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = []
    lines.append(f'🔍 **Guest Login Tracker Report**')
    lines.append(f'⏰ Checked: {now}')
    if since:
        lines.append(f'📅 Since: {since}')
    lines.append('')

    total_new = 0

    # Remote (production — this is the important one)
    if errors.get('remote'):
        lines.append(f'⚠️ **Remote (demos.bowdenneil.com):** Error — {errors["remote"]}')
    else:
        successful = [l for l in remote_logins if l.get('success')]
        failed = [l for l in remote_logins if not l.get('success')]
        lines.append(f'🌐 **Remote (demos.bowdenneil.com):**')
        lines.append(f'  ✅ Successful logins: {len(successful)}')
        lines.append(f'  ❌ Failed attempts: {len(failed)}')
        if successful:
            lines.append('')
            lines.append('  **Recent guest logins:**')
            for login in successful[:10]:
                ip = login.get('ip_address') or 'unknown'
                ua = login.get('user_agent') or 'unknown'
                # Shorten user agent
                ua_short = ua[:60] + '...' if len(ua) > 60 else ua
                ts = login.get('created_at', 'unknown')
                lines.append(f'  • {ts} | IP: {ip} | {ua_short}')
        total_new += len(successful)

    lines.append('')

    # Local
    if errors.get('local'):
        lines.append(f'⚠️ **Local (localhost:8888):** Error — {errors["local"]}')
    else:
        successful = [l for l in local_logins if l.get('success')]
        failed = [l for l in local_logins if not l.get('success')]
        lines.append(f'💻 **Local (localhost:8888):**')
        lines.append(f'  ✅ Successful logins: {len(successful)}')
        lines.append(f'  ❌ Failed attempts: {len(failed)}')
        if successful:
            lines.append('')
            lines.append('  **Recent guest logins:**')
            for login in successful[:5]:
                ip = login.get('ip_address') or 'unknown'
                ts = login.get('created_at', 'unknown')
                lines.append(f'  • {ts} | IP: {ip}')
        total_new += len(successful)

    lines.append('')
    if since:
        if total_new > 0:
            lines.append(f'🔔 **{total_new} new guest login(s) since last check.**')
        else:
            lines.append(f'✅ No new guest logins since last check.')
    else:
        lines.append(f'📊 Total guest logins shown: {total_new}')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Guest login tracker for AI Demos portal')
    parser.add_argument('--all', action='store_true', help='Show all guest logins (not just since last run)')
    parser.add_argument('--days', type=int, help='Show logins from last N days')
    args = parser.parse_args()

    # Determine the "since" timestamp
    since = None
    if args.days:
        since = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d %H:%M:%S')
    elif not args.all:
        since = get_last_run()

    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Query both databases
    local_logins, local_err = query_local_db(since)
    remote_logins, remote_err = query_remote_db(since)

    errors = {'local': local_err, 'remote': remote_err}

    report = format_report(local_logins, remote_logins, since, errors)
    print(report)

    # Save run timestamp (only if not --all or --days)
    if not args.all and not args.days:
        save_run(now_ts)


if __name__ == '__main__':
    main()
