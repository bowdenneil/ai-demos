#!/usr/bin/env python3
"""Generate synthetic GMQ lighting telemetry data into SQLite."""
import sqlite3
import random
import time
import math
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = '/home/ai-demos/gmq_telemetry.db'

ROOMS = [
    'Open Office A', 'Open Office B', 'Meeting Room 1', 'Meeting Room 2',
    'Collab Space', 'Kitchen', 'Corridor North', 'Corridor South',
    'Quiet Room', 'Reception', 'Phone Booth 1', 'Phone Booth 2',
]

EMERGENCY_DEVICES = [f'EMG-{i:02d}' for i in range(1, 13)]

def init_db(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS energy_readings (
            timestamp TEXT NOT NULL,
            room TEXT NOT NULL,
            power_kw REAL NOT NULL,
            dim_level INTEGER NOT NULL,
            occupancy INTEGER NOT NULL,
            daylight_pct INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fixture_status (
            timestamp TEXT NOT NULL,
            dali_address INTEGER NOT NULL,
            room TEXT NOT NULL,
            fixture_type TEXT NOT NULL,
            state TEXT NOT NULL,
            dim_level INTEGER NOT NULL,
            power_kw REAL NOT NULL,
            fault INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS emergency_tests (
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            test_type TEXT NOT NULL,
            result TEXT NOT NULL,
            battery_pct INTEGER NOT NULL,
            signal_strength INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT NOT NULL,
            total_energy_kwh REAL NOT NULL,
            baseline_energy_kwh REAL NOT NULL,
            savings_kwh REAL NOT NULL,
            savings_pct REAL NOT NULL,
            co2_saved_kg REAL NOT NULL,
            cost_saved_eur REAL NOT NULL,
            active_fixtures INTEGER NOT NULL,
            fault_count INTEGER NOT NULL,
            emergency_pass_rate REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_energy_ts ON energy_readings(timestamp);
        CREATE INDEX IF NOT EXISTS idx_fixture_ts ON fixture_status(timestamp);
        CREATE INDEX IF NOT EXISTS idx_emergency_ts ON emergency_tests(timestamp);
    ''')
    conn.commit()

def get_room_power(room, hour, minute):
    """Simulate realistic power consumption based on time of day."""
    # Base load patterns
    if hour < 6 or hour >= 20:
        base = 0.05  # Night: minimal
    elif hour < 8:
        base = 0.15 + (hour - 6) * 0.1  # Morning ramp-up
    elif hour < 12:
        base = 0.6 + random.uniform(-0.1, 0.1)  # Morning work
    elif hour < 13:
        base = 0.4 + random.uniform(-0.05, 0.05)  # Lunch dip
    elif hour < 18:
        base = 0.65 + random.uniform(-0.1, 0.1)  # Afternoon work
    else:
        base = 0.3 - (hour - 18) * 0.1  # Evening wind-down

    # Room-specific multipliers
    room_mult = {
        'Open Office A': 2.5, 'Open Office B': 2.5,
        'Meeting Room 1': 0.8, 'Meeting Room 2': 0.8,
        'Collab Space': 1.5, 'Kitchen': 1.2,
        'Corridor North': 0.6, 'Corridor South': 0.6,
        'Quiet Room': 0.5, 'Reception': 1.0,
        'Phone Booth 1': 0.3, 'Phone Booth 2': 0.3,
    }
    mult = room_mult.get(room, 1.0)

    # Daylight harvesting (window rooms)
    is_window = room in ('Open Office A', 'Open Office B', 'Reception', 'Collab Space')
    daylight = 0
    if is_window and 8 <= hour <= 17:
        daylight = max(0, math.sin((hour - 8) / 9 * math.pi) * 100)
        daylight += random.uniform(-10, 10)
        daylight = max(0, min(100, int(daylight)))
        base *= (1 - daylight / 100 * 0.4)

    # Occupancy
    occupancy = 1 if (8 <= hour <= 18 and random.random() > 0.15) else 0
    if not occupancy and hour >= 20:
        base *= 0.1

    dim = max(0, min(100, int(base / mult * 100)))
    power = base * mult

    return round(power, 3), dim, occupancy, daylight

def generate_energy_reading(conn, ts):
    for room in ROOMS:
        power, dim, occ, daylight = get_room_power(room, ts.hour, ts.minute)
        conn.execute(
            'INSERT INTO energy_readings VALUES (?, ?, ?, ?, ?, ?)',
            (ts.strftime('%Y-%m-%d %H:%M:%S'), room, power, dim, occ, daylight)
        )

def generate_fixture_status(conn, ts):
    addr = 0
    for room in ROOMS:
        fixture_counts = {'Open Office A': 6, 'Open Office B': 6, 'Meeting Room 1': 2,
                         'Meeting Room 2': 2, 'Collab Space': 4, 'Kitchen': 3,
                         'Corridor North': 3, 'Corridor South': 5, 'Quiet Room': 2,
                         'Reception': 3, 'Phone Booth 1': 1, 'Phone Booth 2': 1}
        count = fixture_counts.get(room, 2)
        power, dim, occ, daylight = get_room_power(room, ts.hour, ts.minute)
        for i in range(count):
            is_emg = (addr % 7 == 6)
            ftype = 'Emergency' if is_emg else 'LED Driver'
            if is_emg:
                state = 'emergency'
                fdim = 100
                fpower = 0.08
                fault = 0
            else:
                state = 'on' if power > 0.01 else 'off'
                fdim = dim
                fpower = power / count if count > 0 else 0
                fault = 1 if random.random() > 0.98 else 0
                if fault:
                    state = 'fault'
            conn.execute(
                'INSERT INTO fixture_status VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (ts.strftime('%Y-%m-%d %H:%M:%S'), addr, room, ftype, state, fdim, round(fpower, 3), fault)
            )
            addr += 1

def generate_emergency_test(conn, ts):
    for dev in EMERGENCY_DEVICES:
        test_type = random.choice(['Function', 'Duration', 'Function'])
        result = 'PASS' if random.random() > 0.05 else 'FAIL'
        battery = random.randint(85, 100) if result == 'PASS' else random.randint(40, 70)
        signal = random.randint(2, 4)
        conn.execute(
            'INSERT INTO emergency_tests VALUES (?, ?, ?, ?, ?, ?)',
            (ts.strftime('%Y-%m-%d %H:%M:%S'), dev, test_type, result, battery, signal)
        )

def generate_daily_summary(conn, date_str):
    row = conn.execute('SELECT SUM(power_kw) FROM energy_readings WHERE timestamp LIKE ?', (date_str + '%',)).fetchone()
    total = row[0] or 0
    # Approximate kWh (readings are every 5 min, so divide by 12)
    total_kwh = total / 12
    baseline_kwh = 211.0  # from proposal: 211 MWh/year / 365 = 0.578 MWh/day, but let's use the full baseline
    baseline_daily = 211.0 / 365 * 1000  # kWh per day
    savings = max(0, baseline_daily - total_kwh)
    savings_pct = (savings / baseline_daily * 100) if baseline_daily > 0 else 0
    co2 = savings * 0.1978  # 197.8 gCO2/kWh
    cost = savings * 0.28  # €0.28/kWh

    fault_row = conn.execute('SELECT COUNT(*) FROM fixture_status WHERE timestamp LIKE ? AND fault=1', (date_str + '%',)).fetchone()
    faults = fault_row[0] if fault_row else 0

    active_row = conn.execute('SELECT COUNT(DISTINCT dali_address) FROM fixture_status WHERE timestamp LIKE ? AND state="on"', (date_str + '%',)).fetchone()
    active = active_row[0] if active_row else 0

    emg_row = conn.execute('SELECT COUNT(*) FROM emergency_tests WHERE timestamp LIKE ?', (date_str + '%',)).fetchone()
    emg_total = emg_row[0] if emg_row else 1
    emg_pass = conn.execute('SELECT COUNT(*) FROM emergency_tests WHERE timestamp LIKE ? AND result="PASS"', (date_str + '%',)).fetchone()[0]
    emg_rate = emg_pass / emg_total if emg_total > 0 else 1.0

    conn.execute(
        'INSERT OR REPLACE INTO daily_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (date_str, round(total_kwh, 1), round(baseline_daily, 1), round(savings, 1),
         round(savings_pct, 1), round(co2, 1), round(cost, 2), active, faults, round(emg_rate, 2))
    )

def backfill(conn, days=7):
    """Generate historical data for the past N days."""
    now = datetime.utcnow()
    for d in range(days, 0, -1):
        day = now - timedelta(days=d)
        # Generate readings every 5 minutes
        for minute in range(0, 24 * 60, 5):
            ts = day + timedelta(minutes=minute)
            generate_energy_reading(conn, ts)
            generate_fixture_status(conn, ts)
        # Emergency tests: 2-3 per day
        for _ in range(random.randint(2, 3)):
            test_ts = day + timedelta(hours=random.randint(8, 18), minutes=random.randint(0, 59))
            generate_emergency_test(conn, test_ts)
        generate_daily_summary(conn, day.strftime('%Y-%m-%d'))
    conn.commit()

def append_latest(conn):
    """Generate a single latest reading (for live updates)."""
    ts = datetime.utcnow()
    generate_energy_reading(conn, ts)
    generate_fixture_status(conn, ts)
    if random.random() > 0.7:
        generate_emergency_test(conn, ts)
    generate_daily_summary(conn, ts.strftime('%Y-%m-%d'))
    conn.commit()

if __name__ == '__main__':
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Check if we already have data
    count = conn.execute('SELECT COUNT(*) FROM energy_readings').fetchone()[0]
    if count == 0:
        print('Backfilling 7 days of data...')
        backfill(conn, 7)
        print(f'Backfill complete: {conn.execute("SELECT COUNT(*) FROM energy_readings").fetchone()[0]} energy readings')
    else:
        print(f'Existing data: {count} readings. Appending latest...')
        append_latest(conn)
        print(f'Total now: {conn.execute("SELECT COUNT(*) FROM energy_readings").fetchone()[0]} readings')

    conn.close()
    print('Done.')
