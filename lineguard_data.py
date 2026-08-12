"""
LineGuard AI — Mock data fixtures + telemetry simulator.
Imported by server.py. All data is deterministic for demo consistency.
"""
import math
import random
import time
from datetime import datetime, timedelta

# ─── SITE / LINE ──────────────────────────────────────────────────────────────
SITE_ID = 'SITE-01'
LINE_ID = 'LINE-03'

# ─── ASSETS ──────────────────────────────────────────────────────────────────
ASSETS = {
    'CONVEYOR-01': {
        'id': 'CONVEYOR-01', 'name': 'Conveyor Motor M-101', 'type': 'conveyor_motor',
        'manufacturer': 'Siemens', 'model': 'SIMOTICS-1LE0003',
        'criticality': 'medium', 'location': 'Line 03 — Zone A',
        'install_date': '2023-03-15', 'last_service': '2026-06-20',
        'operating_limits': {
            'vibration_mm_s': {'warn': 3.5, 'crit': 4.5, 'unit': 'mm/s'},
            'temperature_c': {'warn': 70, 'crit': 80, 'unit': '°C'},
            'current_a': {'warn': 13, 'crit': 15, 'unit': 'A'},
        },
        'baselines': {'vibration_mm_s': 2.1, 'temperature_c': 52.0, 'current_a': 8.5},
    },
    'ROBOT-01': {
        'id': 'ROBOT-01', 'name': 'Robotic Arm RA-220', 'type': 'robotic_arm',
        'manufacturer': 'ABB', 'model': 'IRB-4600',
        'criticality': 'high', 'location': 'Line 03 — Zone B',
        'install_date': '2022-11-08', 'last_service': '2026-07-01',
        'operating_limits': {
            'vibration_mm_s': {'warn': 2.8, 'crit': 3.5, 'unit': 'mm/s'},
            'temperature_c': {'warn': 65, 'crit': 75, 'unit': '°C'},
            'cycle_time_s': {'warn': 12.0, 'crit': 14.0, 'unit': 's'},
        },
        'baselines': {'vibration_mm_s': 1.4, 'temperature_c': 44.0, 'cycle_time_s': 10.5},
    },
    'PRESS-02': {
        'id': 'PRESS-02', 'name': 'Hydraulic Press HP-500', 'type': 'hydraulic_press',
        'manufacturer': 'Bosch Rexroth', 'model': 'HDF-500',
        'criticality': 'critical', 'location': 'Line 03 — Zone C',
        'install_date': '2021-07-22', 'last_service': '2026-05-10',
        'operating_limits': {
            'vibration_mm_s': {'warn': 4.5, 'crit': 7.0, 'unit': 'mm/s'},
            'temperature_c': {'warn': 65, 'crit': 80, 'unit': '°C'},
            'pressure_bar': {'warn': 210, 'crit': 230, 'unit': 'bar'},
            'cycle_time_s': {'warn': 8.5, 'crit': 10.0, 'unit': 's'},
        },
        'baselines': {'vibration_mm_s': 3.2, 'temperature_c': 48.0, 'pressure_bar': 200.0, 'cycle_time_s': 7.2},
    },
    'PUMP-03': {
        'id': 'PUMP-03', 'name': 'Cooling Pump CP-330', 'type': 'cooling_pump',
        'manufacturer': 'Grundfos', 'model': 'NB-65',
        'criticality': 'medium', 'location': 'Line 03 — Zone D',
        'install_date': '2023-01-12', 'last_service': '2026-06-15',
        'operating_limits': {
            'vibration_mm_s': {'warn': 3.0, 'crit': 4.0, 'unit': 'mm/s'},
            'temperature_c': {'warn': 60, 'crit': 70, 'unit': '°C'},
            'flow_rate_l_min': {'warn': 120, 'crit': 100, 'unit': 'L/min'},
        },
        'baselines': {'vibration_mm_s': 1.8, 'temperature_c': 38.0, 'flow_rate_l_min': 145.0},
    },
    'PACK-04': {
        'id': 'PACK-04', 'name': 'Packaging Unit PK-400', 'type': 'packaging_unit',
        'manufacturer': 'Krones', 'model': 'Variopac Pro',
        'criticality': 'low', 'location': 'Line 03 — Zone E',
        'install_date': '2023-06-01', 'last_service': '2026-07-15',
        'operating_limits': {
            'vibration_mm_s': {'warn': 2.5, 'crit': 3.5, 'unit': 'mm/s'},
            'temperature_c': {'warn': 55, 'crit': 65, 'unit': '°C'},
            'cycle_time_s': {'warn': 3.0, 'crit': 4.0, 'unit': 's'},
        },
        'baselines': {'vibration_mm_s': 1.2, 'temperature_c': 35.0, 'cycle_time_s': 2.5},
    },
}

# Metrics per asset type
ASSET_METRICS = {
    'conveyor_motor': ['vibration_mm_s', 'temperature_c', 'current_a'],
    'robotic_arm': ['vibration_mm_s', 'temperature_c', 'cycle_time_s'],
    'hydraulic_press': ['vibration_mm_s', 'temperature_c', 'pressure_bar', 'cycle_time_s'],
    'cooling_pump': ['vibration_mm_s', 'temperature_c', 'flow_rate_l_min'],
    'packaging_unit': ['vibration_mm_s', 'temperature_c', 'cycle_time_s'],
}

METRIC_LABELS = {
    'vibration_mm_s': 'Vibration', 'temperature_c': 'Temperature',
    'current_a': 'Current', 'pressure_bar': 'Pressure',
    'cycle_time_s': 'Cycle Time', 'flow_rate_l_min': 'Flow Rate',
}

# ─── TELEMETRY SIMULATOR ─────────────────────────────────────────────────────
# Demo clock — anomaly starts 4 hours ago, advances in real-time after init
DEMO_START_OFFSET_HOURS = 4
TELEMETRY_INTERVAL_S = 5  # seconds between readings

# ─── FAILURE SCENARIOS ───────────────────────────────────────────────────────
# One scenario per asset. A random one is active per session (reset re-rolls).
# primary ramps hardest; secondary ramps gently; fluctuate oscillates with
# growing variance. This gives each asset a distinct, plausible failure story.
FAILURE_SCENARIOS = {
    'CONVEYOR-01': {
        'name': 'Belt misalignment / motor overload',
        'primary': 'current_a', 'secondary': ['temperature_c'], 'fluctuate': ['vibration_mm_s'],
        'part': 'BELT-101-T', 'skill': 'conveyor_alignment',
        'doc_query': 'belt tracking motor current', 'history_query': 'belt alignment',
    },
    'ROBOT-01': {
        'name': 'Joint 3 gearbox backlash',
        'primary': 'cycle_time_s', 'secondary': ['vibration_mm_s'], 'fluctuate': [],
        'part': 'GBX-4600-J3', 'skill': 'robot_calibration',
        'doc_query': 'gearbox backlash joint calibration', 'history_query': 'gearbox',
    },
    'PRESS-02': {
        'name': 'Hydraulic press bearing degradation',
        'primary': 'vibration_mm_s', 'secondary': ['temperature_c', 'cycle_time_s'], 'fluctuate': ['pressure_bar'],
        'part': 'BR-500-A', 'skill': 'bearing_replacement',
        'doc_query': 'bearing vibration', 'history_query': 'bearing',
    },
    'PUMP-03': {
        'name': 'Pump cavitation / impeller wear',
        'primary': 'flow_rate_l_min', 'secondary': ['vibration_mm_s', 'temperature_c'], 'fluctuate': [],
        'part': 'IMP-NB65-S', 'skill': 'pump_overhaul',
        'doc_query': 'cavitation impeller flow', 'history_query': 'impeller',
    },
    'PACK-04': {
        'name': 'Sealing head wear / jam risk',
        'primary': 'cycle_time_s', 'secondary': ['temperature_c'], 'fluctuate': ['vibration_mm_s'],
        'part': 'SEAL-PK4-H', 'skill': 'packaging_service',
        'doc_query': 'sealing head cycle time', 'history_query': 'sealing',
    },
}

# Mutable anomaly state — random asset per server start, re-rolled on reset
_anomaly_state = {
    'asset_id': random.choice(list(FAILURE_SCENARIOS.keys())),
    'started_at': time.time() - DEMO_START_OFFSET_HOURS * 3600,
    'escalation_boost': 0.0,   # added by the Escalate demo button
}

def get_active_scenario():
    """The currently active failure scenario."""
    aid = _anomaly_state['asset_id']
    return {'asset_id': aid, **FAILURE_SCENARIOS[aid]}

def escalate_anomaly():
    """Demo button: visibly accelerate the ramp. Stacks up to +0.45."""
    _anomaly_state['escalation_boost'] = min(0.45, _anomaly_state['escalation_boost'] + 0.15)
    return _anomaly_state['escalation_boost']

def reroll_anomaly():
    """Reset: pick a fresh random asset and restart the 4h ramp."""
    _anomaly_state['asset_id'] = random.choice(list(FAILURE_SCENARIOS.keys()))
    _anomaly_state['started_at'] = time.time() - DEMO_START_OFFSET_HOURS * 3600
    _anomaly_state['escalation_boost'] = 0.0
    return _anomaly_state['asset_id']

def _anomaly_factor(timestamp, asset_id):
    """Return 0.0 (normal) to 1.0 (severe) for the active anomaly asset."""
    if asset_id != _anomaly_state['asset_id']:
        return 0.0
    anomaly_age = timestamp - _anomaly_state['started_at']
    if anomaly_age <= 0:
        return 0.0
    factor = anomaly_age / (4 * 3600) + _anomaly_state['escalation_boost']
    return min(max(factor, 0.0), 1.0)

def _add_noise(base, amplitude, seed_offset=0):
    """Deterministic noise based on time."""
    t = time.time() + seed_offset
    return base + math.sin(t * 0.7) * amplitude * 0.3 + math.sin(t * 1.3) * amplitude * 0.2 + (random.random() - 0.5) * amplitude * 0.1

def generate_telemetry(asset_id, metric, timestamp=None):
    """Generate a single telemetry reading for an asset/metric at a given time."""
    if timestamp is None:
        timestamp = time.time()
    asset = ASSETS[asset_id]
    baseline = asset['baselines'].get(metric)
    if baseline is None:
        return None
    limits = asset['operating_limits'].get(metric, {})
    warn = limits.get('warn', baseline * 1.5)
    crit = limits.get('crit', baseline * 2.0)

    anomaly = _anomaly_factor(timestamp, asset_id)

    value = baseline
    if anomaly > 0:
        sc = FAILURE_SCENARIOS[asset_id]
        # flow_rate degrades DOWNWARD (cavitation starves flow); everything else ramps up
        if metric == sc['primary']:
            if metric == 'flow_rate_l_min':
                value = baseline - (baseline - (limits.get('warn', baseline * 0.8))) * 0.5 * anomaly - baseline * 0.15 * anomaly * anomaly
            else:
                value = baseline + (warn - baseline) * 0.4 * anomaly + (crit - baseline) * 0.7 * anomaly * anomaly
        elif metric in sc['secondary']:
            value = baseline + (warn - baseline) * 0.5 * anomaly
        elif metric in sc['fluctuate']:
            value = baseline + math.sin(timestamp * 0.05) * (2 + 8 * anomaly) + (random.random() - 0.5) * (1 + 3 * anomaly)

    # Add noise
    noise_amp = (crit - baseline) * 0.03
    value = _add_noise(value, noise_amp, hash(asset_id + metric) % 100)

    # Status: flow_rate is a lower-is-bad metric
    if metric == 'flow_rate_l_min':
        low_warn = limits.get('warn', baseline * 0.85)
        low_crit = limits.get('crit', baseline * 0.7)
        status = 'critical' if value <= low_crit else 'warning' if value <= low_warn else 'normal'
    else:
        status = 'critical' if value >= crit else 'warning' if value >= warn else 'normal'
    
    return {
        'asset_id': asset_id,
        'metric': metric,
        'value': round(value, 2),
        'unit': limits.get('unit', ''),
        'timestamp': timestamp,
        'iso_time': datetime.fromtimestamp(timestamp).strftime('%H:%M:%S'),
        'status': status,
        'baseline': baseline,
        'warn_threshold': warn,
        'crit_threshold': crit,
        'anomaly_factor': round(anomaly, 3),
    }

def generate_series(asset_id, metric, points=60, interval=None):
    """Generate a time series of readings."""
    if interval is None:
        interval = TELEMETRY_INTERVAL_S
    now = time.time()
    series = []
    for i in range(points):
        t = now - (points - 1 - i) * interval
        reading = generate_telemetry(asset_id, metric, t)
        if reading:
            series.append(reading)
    return series

def get_asset_snapshot(asset_id):
    """Current readings for all metrics of an asset."""
    metrics = ASSET_METRICS.get(ASSETS[asset_id]['type'], [])
    readings = {}
    overall_status = 'normal'
    anomaly_count = 0
    for m in metrics:
        r = generate_telemetry(asset_id, m)
        if r:
            readings[m] = r
            if r['status'] == 'critical':
                overall_status = 'critical'
                anomaly_count += 1
            elif r['status'] == 'warning' and overall_status != 'critical':
                overall_status = 'warning'
                anomaly_count += 1
    return {
        'asset_id': asset_id,
        'asset': ASSETS[asset_id],
        'metrics': readings,
        'overall_status': overall_status,
        'anomaly_count': anomaly_count,
        'timestamp': time.time(),
    }

def list_active_anomalies(site_id):
    """List assets with active anomalies across the line."""
    anomalies = []
    for asset_id in ASSETS:
        snap = get_asset_snapshot(asset_id)
        if snap['overall_status'] != 'normal':
            for m, r in snap['metrics'].items():
                if r['status'] != 'normal':
                    anomalies.append({
                        'asset_id': asset_id,
                        'asset_name': ASSETS[asset_id]['name'],
                        'metric': m,
                        'metric_label': METRIC_LABELS.get(m, m),
                        'value': r['value'],
                        'unit': r['unit'],
                        'status': r['status'],
                        'baseline': r['baseline'],
                        'deviation_pct': round((r['value'] - r['baseline']) / r['baseline'] * 100, 1) if r['baseline'] else 0,
                        'timestamp': r['iso_time'],
                    })
    return anomalies

# ─── MAINTENANCE HISTORY ─────────────────────────────────────────────────────
MAINTENANCE_HISTORY = [
    {
        'id': 'WO-2025-0847', 'asset_id': 'PRESS-02',
        'date': '2025-09-14', 'type': 'corrective',
        'description': 'Replaced main bearing assembly on hydraulic press motor. Bearing showed spalling on outer race.',
        'root_cause': 'Bearing degradation due to lubrication breakdown',
        'downtime_hours': 6.5, 'cost_eur': 4200,
        'technician': 'M. Schneider', 'parts_used': ['Bearing kit BR-500-A', 'Seal kit SK-220'],
        'outcome': 'Press returned to normal operation. Vibration dropped from 5.8 to 3.1 mm/s.',
    },
    {
        'id': 'WO-2026-0312', 'asset_id': 'PRESS-02',
        'date': '2026-05-10', 'type': 'preventive',
        'description': 'Scheduled 500-hour service. Replaced hydraulic fluid, inspected bearings, calibrated pressure sensors.',
        'root_cause': 'Scheduled maintenance',
        'downtime_hours': 2.0, 'cost_eur': 850,
        'technician': 'M. Schneider', 'parts_used': ['Hydraulic fluid ISO VG 46 — 40L', 'Filter element F-120'],
        'outcome': 'All readings within spec. Bearing inspection noted minor wear on inner race.',
    },
    {
        'id': 'WO-2026-0489', 'asset_id': 'ROBOT-01',
        'date': '2026-07-01', 'type': 'preventive',
        'description': 'Quarterly inspection and grease replacement for J1-J3 axes.',
        'root_cause': 'Scheduled maintenance',
        'downtime_hours': 1.5, 'cost_eur': 400,
        'technician': 'L. Bauer', 'parts_used': ['Grease Mobilux EP2 — 2kg'],
        'outcome': 'All axes within tolerance. No anomalies detected.',
    },
    {
        'id': 'WO-2025-0611', 'asset_id': 'ROBOT-01',
        'date': '2025-10-14', 'type': 'corrective',
        'description': 'Joint 3 gearbox replaced after backlash exceeded 0.4mm. Path repeatability degraded, cycle time drifting up.',
        'root_cause': 'Gearbox wear — backlash beyond spec',
        'downtime_hours': 5.5, 'cost_eur': 3200,
        'technician': 'L. Bauer', 'parts_used': ['Gearbox assembly GBX-4600-J3'],
        'outcome': 'Repeatability restored to ±0.05mm. Cycle time back to 10.5s baseline.',
    },
    {
        'id': 'WO-2025-0733', 'asset_id': 'CONVEYOR-01',
        'date': '2025-12-02', 'type': 'corrective',
        'description': 'Belt re-tracked and tensioned after edge fraying. Motor current elevated 15% before fix.',
        'root_cause': 'Belt misalignment increasing motor load',
        'downtime_hours': 2.0, 'cost_eur': 450,
        'technician': 'L. Bauer', 'parts_used': ['Tracking rollers x2'],
        'outcome': 'Current returned to 8.5A baseline. Belt wear within limits.',
    },
    {
        'id': 'WO-2025-0902', 'asset_id': 'PUMP-03',
        'date': '2026-02-18', 'type': 'corrective',
        'description': 'Impeller replaced after cavitation damage. Flow rate had dropped 20% with rising vibration.',
        'root_cause': 'Cavitation — suction line restriction from partially closed valve',
        'downtime_hours': 3.0, 'cost_eur': 780,
        'technician': 'M. Schneider', 'parts_used': ['Impeller + wear ring set IMP-NB65-S'],
        'outcome': 'Flow restored to 145 L/min. Suction valve interlock added to prevent recurrence.',
    },
    {
        'id': 'WO-2026-0104', 'asset_id': 'PACK-04',
        'date': '2026-04-09', 'type': 'corrective',
        'description': 'Sealing head serviced after intermittent film jams. Cycle time had crept from 4.2s to 5.1s.',
        'root_cause': 'Sealing head wear — heater band degradation',
        'downtime_hours': 1.5, 'cost_eur': 320,
        'technician': 'A. Kowalski', 'parts_used': ['Sealing head service kit SEAL-PK4-H'],
        'outcome': 'Cycle time restored. Recommended 6-month head service interval.',
    },
]

def search_maintenance_history(asset_id, query=''):
    """Search maintenance history for an asset."""
    results = [r for r in MAINTENANCE_HISTORY if r['asset_id'] == asset_id]
    if query:
        q = query.lower()
        results = [r for r in results if q in r['description'].lower() or q in r['root_cause'].lower() or q in r['outcome'].lower()]
    return results

# ─── TECHNICAL DOCUMENTS ─────────────────────────────────────────────────────
TECHNICAL_DOCS = [
    {
        'id': 'DOC-BR-001', 'title': 'Bearing Inspection Procedure — HP-500',
        'asset_id': 'PRESS-02',
        'content': """BEARING INSPECTION PROCEDURE — Hydraulic Press HP-500

1. SAFETY: Lockout/tagout hydraulic press before inspection. Verify zero residual pressure.
2. ACCESS: Remove motor housing cover (4x M10 bolts). Document torque values.
3. VISUAL: Inspect bearing races for spalling, pitting, or discoloration.
   - Outer race: Check for axial wear patterns.
   - Inner race: Check for heat discoloration (blue/brown tint).
   - Rolling elements: Check for surface fatigue.
4. MEASUREMENT: Use dial indicator to measure radial play.
   - Spec: < 0.05mm for BR-500-A bearing.
   - Replace if > 0.08mm.
5. LUBRICATION: Inspect grease condition. Water ingress or burnt smell indicates degradation.
6. REASSEMBLY: Torque bolts to 45 Nm in cross pattern. Verify alignment.
7. POST-TEST: Run press unloaded for 5 minutes. Vibration should return to < 3.5 mm/s.

TROUBLESHOOTING:
- High vibration + rising temperature → bearing degradation (most common).
- High vibration + pressure fluctuation → hydraulic system issue.
- Rising temperature + normal vibration → cooling system issue.

COMPATIBLE PARTS:
- BR-500-A: OEM bearing kit (Bosch Rexroth)
- BR-500-B: Aftermarket equivalent (SKF)

ESTIMATED TIME: 55 minutes (with qualified technician)
LOCKOUT REQUIRED: Yes — full hydraulic depressurization""",
        'sections': ['Safety', 'Access', 'Visual Inspection', 'Measurement', 'Lubrication', 'Reassembly', 'Post-Test', 'Troubleshooting'],
    },
    {
        'id': 'DOC-HP-002', 'title': 'Hydraulic Press Troubleshooting Guide',
        'asset_id': 'PRESS-02',
        'content': """HYDRAULIC PRESS HP-500 — TROUBLESHOOTING GUIDE

SYMPTOM MATRIX:
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Rising vibration | Bearing wear | Inspect bearing, replace if needed |
| Rising temperature | Fluid degradation or cooling issue | Check fluid level/quality, inspect cooler |
| Pressure fluctuation | Valve wear or seal degradation | Inspect proportional valves |
| Extended cycle time | Valve response lag or bearing drag | Check valve timing, inspect bearings |
| Unusual noise | Bearing or pump cavitation | Immediate inspection required |

FAILURE MODE ANALYSIS:
- Bearing degradation is the most common failure mode for HP-500 presses.
- Typical progression: vibration increase → temperature rise → cycle time extension → pressure fluctuation.
- Time to failure from first sign: typically 2-6 weeks under continuous operation.
- Historical data shows 78% of HP-500 bearing failures follow this pattern.

MAINTENANCE WINDOW:
- Minimum window: 45 minutes (inspection only)
- Full bearing replacement: 55 minutes (with qualified technician and parts)
- Recommended: schedule during production changeover to minimize downtime impact.

PARTS REQUIRED FOR BEARING REPLACEMENT:
- Bearing kit BR-500-A (OEM) or BR-500-B (aftermarket)
- Seal kit SK-220
- Hydraulic fluid top-up (ISO VG 46, ~5L)

QUALIFICATIONS:
- Technician must hold Level 2 Hydraulic Systems certification
- Lockout/tagout authorization required""",
        'sections': ['Symptom Matrix', 'Failure Mode Analysis', 'Maintenance Window', 'Parts Required', 'Qualifications'],
    },
    {
        'id': 'DOC-CV-001', 'title': 'Conveyor Motor M-101 — Belt & Motor Service Guide',
        'asset_id': 'CONVEYOR-01',
        'content': """CONVEYOR M-101 SERVICE GUIDE

SYMPTOM MATRIX:
| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Rising motor current | Belt misalignment or over-tension | Re-track belt, check tension |
| Rising temperature | Motor overload from belt drag | Reduce load, inspect belt path |
| Squealing under load | Belt slip or edge fraying | Inspect belt edges, re-track |

BELT RE-TRACKING: 30-45 minutes. Requires conveyor_alignment skill.
PARTS: BELT-101-T (belt + tracking kit) for full replacement (90 min).
Motor current above 13A sustained indicates urgent intervention — thermal
trip at 15A will hard-stop the line.""",
        'sections': ['Symptom Matrix', 'Re-tracking', 'Parts'],
    },
    {
        'id': 'DOC-RB-001', 'title': 'IRB-4600 Joint Gearbox — Backlash Diagnosis',
        'asset_id': 'ROBOT-01',
        'content': """ABB IRB-4600 GEARBOX DIAGNOSIS

SYMPTOMS OF GEARBOX BACKLASH:
- Cycle time drift upward (controller compensates with slower moves)
- Vibration during high-speed arcs
- Placement repeatability degradation (>±0.1mm)
- Clicking noise at direction reversals

MEASUREMENT: Dial test on J3 flange. Spec < 0.15mm. Replace gearbox > 0.3mm.
REPLACEMENT: GBX-4600-J3 assembly, 4-6 hours, robot_calibration skill +
post-replacement calibration routine (mastering + repeatability test).
HISTORY NOTE: J3 gearbox on this unit replaced 2025-10 (WO-2025-0611) —
premature re-wear may indicate load/duty-cycle issue, consider duty review.""",
        'sections': ['Symptoms', 'Measurement', 'Replacement'],
    },
    {
        'id': 'DOC-PM-001', 'title': 'NB-65 Pump — Cavitation & Impeller Wear Guide',
        'asset_id': 'PUMP-03',
        'content': """GRUNDFOS NB-65 CAVITATION GUIDE

CAVITATION SIGNATURE:
- Falling flow rate with rattling/gravel noise
- Rising vibration at pump inlet
- Elevated bearing temperature (secondary)

CAUSES: Suction restriction (valve, strainer), low NPSH, air ingress.
CHECK FIRST: Suction valve position and strainer — 15 min, no parts.
IMPELLER REPLACEMENT: IMP-NB65-S set, 2.5-3 hours, pump_overhaul skill.
HISTORY NOTE: Cavitation event 2026-02 (WO-2025-0902) traced to partially
closed suction valve — interlock added; verify interlock before tear-down.""",
        'sections': ['Signature', 'Causes', 'Replacement'],
    },
    {
        'id': 'DOC-PK-001', 'title': 'Variopac Sealing Head — Wear & Jam Prevention',
        'asset_id': 'PACK-04',
        'content': """KRONES VARIOPAC SEALING HEAD GUIDE

WEAR PROGRESSION:
- Cycle time creep (head dwell compensation)
- Intermittent film jams
- Weak/incomplete seals on random packs
- Heater band temperature instability

SERVICE: SEAL-PK4-H kit (head plates + heater bands + film guides),
60-90 minutes, packaging_service skill.
INTERVAL: 6 months recommended (see WO-2026-0104 outcome).
JAM RISK: Cycle time above 5.5s correlates with jam probability >30% —
schedule service before that threshold.""",
        'sections': ['Wear Progression', 'Service', 'Jam Risk'],
    },
]

def search_technical_documents(asset_id, query=''):
    """Search technical documents for an asset."""
    results = [d for d in TECHNICAL_DOCS if d['asset_id'] == asset_id]
    if query:
        q = query.lower()
        results = [d for d in results if q in d['content'].lower() or q in d['title'].lower()]
    return results

# ─── PRODUCTION SCHEDULE ────────────────────────────────────────────────────
PRODUCTION_SCHEDULE = {
    'line_id': LINE_ID,
    'date': datetime.now().strftime('%Y-%m-%d'),
    'shifts': [
        {'shift': 'Morning', 'start': '06:00', 'end': '14:00', 'product': 'Product A — Steel brackets', 'status': 'completed'},
        {'shift': 'Afternoon', 'start': '14:00', 'end': '22:00', 'product': 'Product B — Aluminium panels', 'status': 'in_progress'},
        {'shift': 'Night', 'start': '22:00', 'end': '06:00', 'product': 'Product C — Copper connectors', 'status': 'scheduled'},
    ],
    'changeovers': [
        {
            'id': 'CO-2026-0811-01',
            'start': datetime.now().replace(hour=datetime.now().hour + 1, minute=30, second=0, microsecond=0).strftime('%H:%M'),
            'end': datetime.now().replace(hour=datetime.now().hour + 2, minute=45, second=0, microsecond=0).strftime('%H:%M'),
            'duration_minutes': 75,
            'from_product': 'Product B — Aluminium panels',
            'to_product': 'Product C — Copper connectors',
            'status': 'scheduled',
            'available_for_maintenance': True,
            'max_maintenance_minutes': 60,
        },
    ],
    'line_throughput_units_per_hour': 240,
    'line_utilization_pct': 87,
}

def get_production_schedule(line_id, date_str=None):
    return PRODUCTION_SCHEDULE

# ─── INVENTORY ───────────────────────────────────────────────────────────────
INVENTORY = [
    {
        'part_number': 'BR-500-A', 'description': 'Bearing kit (OEM) — Bosch Rexroth HP-500',
        'quantity': 1, 'location': 'Spare parts store — Shelf B-12',
        'lead_time_days': 14, 'cost_eur': 380,
        'compatible_assets': ['PRESS-02'],
    },
    {
        'part_number': 'BR-500-B', 'description': 'Bearing kit (aftermarket) — SKF equivalent',
        'quantity': 0, 'location': 'Spare parts store — Shelf B-13',
        'lead_time_days': 5, 'cost_eur': 290,
        'compatible_assets': ['PRESS-02'],
    },
    {
        'part_number': 'SK-220', 'description': 'Seal kit for HP-500 hydraulic press',
        'quantity': 3, 'location': 'Spare parts store — Shelf C-08',
        'lead_time_days': 7, 'cost_eur': 95,
        'compatible_assets': ['PRESS-02'],
    },
    {
        'part_number': 'ISO-VG-46', 'description': 'Hydraulic fluid ISO VG 46 (20L drum)',
        'quantity': 4, 'location': 'Fluids store — Drum rack D-01',
        'lead_time_days': 2, 'cost_eur': 120,
        'compatible_assets': ['PRESS-02', 'PUMP-03'],
    },
    {
        'part_number': 'BELT-101-T', 'description': 'Conveyor belt + tracking kit — SIMOTICS M-101',
        'quantity': 2, 'location': 'Spare parts store — Shelf A-04',
        'lead_time_days': 3, 'cost_eur': 210,
        'compatible_assets': ['CONVEYOR-01'],
    },
    {
        'part_number': 'GBX-4600-J3', 'description': 'Joint 3 gearbox assembly — ABB IRB-4600',
        'quantity': 1, 'location': 'Spare parts store — Shelf E-02',
        'lead_time_days': 21, 'cost_eur': 1450,
        'compatible_assets': ['ROBOT-01'],
    },
    {
        'part_number': 'IMP-NB65-S', 'description': 'Impeller + wear ring set — Grundfos NB-65',
        'quantity': 1, 'location': 'Spare parts store — Shelf D-07',
        'lead_time_days': 10, 'cost_eur': 520,
        'compatible_assets': ['PUMP-03'],
    },
    {
        'part_number': 'SEAL-PK4-H', 'description': 'Sealing head service kit — Krones Variopac',
        'quantity': 3, 'location': 'Spare parts store — Shelf F-11',
        'lead_time_days': 4, 'cost_eur': 175,
        'compatible_assets': ['PACK-04'],
    },
]

# Track delayed parts (can be modified during demo)
_delayed_parts = set()

def get_inventory(part_number=None):
    """Get inventory records."""
    results = []
    for item in INVENTORY:
        record = dict(item)
        if item['part_number'] in _delayed_parts:
            record['quantity'] = 0
            record['status'] = 'delayed'
            record['delay_note'] = f'Shipment delayed by 2 hours. Expected arrival in ~120 minutes. Supplier confirmed shipment is in transit.'
        elif item['quantity'] > 0:
            record['status'] = 'in_stock'
        else:
            record['status'] = 'out_of_stock'
        if part_number is None or item['part_number'] == part_number:
            results.append(record)
    return results

def delay_part(part_number):
    """Mark a part as delayed (for demo event injection)."""
    _delayed_parts.add(part_number)

def reset_delays():
    _delayed_parts.clear()

# ─── TECHNICIANS ─────────────────────────────────────────────────────────────
TECHNICIANS = [
    {
        'id': 'TECH-001', 'name': 'Marcus Schneider', 'skills': ['hydraulic_systems', 'bearing_replacement', 'lockout_tagout', 'pump_overhaul'],
        'certification_level': 3, 'available': True,
        'shift_end': '22:00', 'current_location': 'Line 03 — Zone C (nearby)',
        'next_available': 'now', 'estimated_travel_min': 2,
    },
    {
        'id': 'TECH-002', 'name': 'Lukas Bauer', 'skills': ['robotic_systems', 'robot_calibration', 'electrical', 'conveyor_alignment'],
        'certification_level': 2, 'available': True,
        'shift_end': '22:00', 'current_location': 'Line 02 — Zone A',
        'next_available': 'now', 'estimated_travel_min': 10,
    },
    {
        'id': 'TECH-003', 'name': 'Anna Kowalski', 'skills': ['hydraulic_systems', 'welding', 'packaging_service'],
        'certification_level': 2, 'available': False,
        'shift_end': '18:00', 'current_location': 'Off-site — training',
        'next_available': 'tomorrow 06:00', 'estimated_travel_min': 60,
    },
]

def get_technician_availability(skill=None, window=None):
    """Find available technicians, optionally filtered by skill."""
    results = []
    for tech in TECHNICIANS:
        record = dict(tech)
        if skill and skill not in tech['skills']:
            record['qualified'] = False
        else:
            record['qualified'] = True
        results.append(record)
    # Sort: qualified first, then available
    results.sort(key=lambda t: (not t['qualified'], not t['available']))
    return results

# ─── OPERATOR OBSERVATIONS ───────────────────────────────────────────────────
# Scenario-specific observations — served for whichever asset has the anomaly
_SCENARIO_OBSERVATIONS = {
    'CONVEYOR-01': [
        'Belt looks like it\'s tracking slightly off-centre near the drive pulley. Some squealing under load.',
        'Motor housing feels warmer than usual to the touch. No burning smell yet.',
    ],
    'ROBOT-01': [
        'Robot seems slower on the reach-and-place move. Occasional judder at the end of the arc.',
        'Heard a faint clicking from the arm during fast moves. Repeatability seems off — parts placed a few mm out.',
    ],
    'PRESS-02': [
        'Press motor sounds different — higher pitch whine than usual. Started about an hour ago.',
        'Noticed slight hydraulic fluid smell near the press motor area. No visible leaks.',
    ],
    'PUMP-03': [
        'Pump sounds like it\'s gargling — rattling noise that comes and goes. Flow gauge reading lower than this morning.',
        'Pipework near the pump inlet is vibrating more than usual.',
    ],
    'PACK-04': [
        'Film feed jammed twice this shift — had to clear it manually. Sealing looks weaker on some packs.',
        'Packaging unit is running noticeably slower. Queue building up ahead of it.',
    ],
}

def _build_observations():
    """Observations for the active anomaly asset."""
    aid = _anomaly_state['asset_id']
    texts = _SCENARIO_OBSERVATIONS.get(aid, [])
    return [
        {
            'id': f'OBS-{i+1:03d}', 'asset_id': aid, 'operator': 'T. Müller',
            'timestamp': (datetime.now() - timedelta(minutes=60 - i * 30)).strftime('%Y-%m-%d %H:%M'),
            'observation': text, 'severity': 'noted', 'acknowledged': True,
        }
        for i, text in enumerate(texts)
    ]

# Can add new observations during demo
_new_observations = []

def get_operator_observations(asset_id, time_window='4h'):
    """Get operator observations for an asset."""
    base = [o for o in _build_observations() if o['asset_id'] == asset_id]
    return base + [o for o in _new_observations if o['asset_id'] == asset_id]

def add_operator_observation(asset_id, observation, operator='Demo Presenter'):
    """Add a new operator observation (for demo event injection)."""
    obs = {
        'id': f'OBS-{100 + len(_new_observations) + 1:03d}',
        'asset_id': asset_id, 'operator': operator,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'observation': observation, 'severity': 'reported', 'acknowledged': False,
    }
    _new_observations.append(obs)
    return obs

# ─── DOWNTIME IMPACT ─────────────────────────────────────────────────────────
def estimate_downtime_impact(asset_id, duration_minutes):
    """Estimate the financial and operational impact of downtime."""
    asset = ASSETS[asset_id]
    schedule = PRODUCTION_SCHEDULE
    throughput = schedule['line_utilization_pct'] / 100 * schedule['line_throughput_units_per_hour']
    units_lost = throughput * (duration_minutes / 60)
    
    # Revenue per unit varies by product
    revenue_per_unit = {'Product A — Steel brackets': 2.50, 'Product B — Aluminium panels': 4.80, 'Product C — Copper connectors': 1.90}
    current_product = 'Product B — Aluminium panels'  # afternoon shift
    revenue_per_unit_current = revenue_per_unit.get(current_product, 3.00)
    revenue_lost = units_lost * revenue_per_unit_current
    
    # If unplanned (not during changeover), add escalation costs
    planned = duration_minutes <= 60  # fits in changeover
    
    return {
        'asset_id': asset_id,
        'asset_name': asset['name'],
        'duration_minutes': duration_minutes,
        'planned': planned,
        'units_lost': round(units_lost),
        'revenue_lost_eur': round(revenue_lost, 2),
        'line_throughput': throughput,
        'current_product': current_product,
        'revenue_per_unit': revenue_per_unit_current,
        'recommendation': 'Schedule during planned changeover to avoid unplanned downtime costs.' if planned else 'Unplanned — full line stop required. Consider emergency maintenance.',
        'comparison': {
            'maintain_now_during_changeover': {
                'downtime_minutes': duration_minutes,
                'revenue_lost_eur': 0,  # during changeover = no production loss
                'risk': 'low',
            },
            'run_to_failure': {
                'downtime_minutes': duration_minutes * 4,  # emergency repair takes longer
                'revenue_lost_eur': round(revenue_lost * 4, 2),
                'risk': 'high',
                'additional_risks': ['Possible secondary damage to hydraulic system', 'Safety risk to operators', 'May require longer lead time for emergency parts'],
            }
        }
    }

# ─── WORK ORDERS ─────────────────────────────────────────────────────────────
_work_orders = []
_approval_requests = []

def draft_work_order(payload):
    """Draft a work order (does NOT submit — requires approval)."""
    wo_id = f'WO-2026-{len(_work_orders) + 500:04d}'
    wo = {
        'id': wo_id,
        'status': 'draft',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'requires_approval': True,
        **payload,
    }
    _work_orders.append(wo)
    return wo

def send_approval_request(payload):
    """Send an approval request for a work order."""
    apr_id = f'APR-2026-{len(_approval_requests) + 100:04d}'
    apr = {
        'id': apr_id,
        'status': 'pending',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'approver_role': 'maintenance_supervisor',
        'requires_human_decision': True,
        **payload,
    }
    _approval_requests.append(apr)
    return apr

def get_work_orders():
    return _work_orders

def reset_state():
    """Reset all mutable state for a fresh demo. Re-rolls the anomaly asset."""
    _work_orders.clear()
    _approval_requests.clear()
    _new_observations.clear()
    reset_delays()
    return reroll_anomaly()
