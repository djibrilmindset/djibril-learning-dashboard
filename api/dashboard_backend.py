#!/usr/bin/env python3
"""
ADELLE DASHBOARD BACKEND — Données réelles temps réel
Lit: provider_health.json, proxy_cache/, logs cron, Supabase, processus locaux
"""
import os, sys, json, subprocess, time, glob, re
from datetime import datetime, timedelta
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── CONFIG ──
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SB_HEADERS = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'}

BASE_DIR = os.path.expanduser('~/agence-ia')
STATE_DIR = os.path.expanduser('~/.hermes')

AGENTS_LOC = [
    ('MANAGER', 'agence-ia/manager/manager.py', 8788),
    ('TRACKING', 'agence-ia/tracking/tracking_agent.py', None),
    ('ADELLE', 'hermes-agent', None),
    ('WEBHOOK-MEDIA', 'tg_media_webhook.py', 8790),
    ('ORCHESTRATOR', 'orchestrator_proxy.py', 8788),
]

PROXY_URL = 'http://localhost:8788'
N8N_URL = 'http://localhost:5678'

import requests

# ── HELPERS ──
def sb_get(table, query='limit=100'):
    try:
        r = requests.get(f'{SUPABASE_URL}/rest/v1/{table}?{query}', headers=SB_HEADERS, timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        return {'error': str(e)}

def process_status(name, pattern, port):
    try:
        proc = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True)
        pid = proc.stdout.strip().split('\n')[0] if proc.stdout.strip() else None
        status = 'healthy' if pid else 'dead'
        if port and status == 'healthy':
            try:
                r = requests.get(f'http://localhost:{port}/health', timeout=2)
                if r.status_code != 200: status = 'stale'
            except: status = 'stale'
        return {'name': name, 'pid': pid, 'status': status, 'last_ping': datetime.utcnow().isoformat()}
    except Exception as e:
        return {'name': name, 'status': 'dead', 'error': str(e)}

def read_provider_health():
    try:
        with open(f'{BASE_DIR}/state/provider_health.json') as f:
            return json.load(f)
    except: return {}

def read_proxy_calls_24h():
    """Lit le cache proxy pour estimer les appels 24h"""
    cache_dir = f'{BASE_DIR}/state/proxy_cache'
    if not os.path.exists(cache_dir): return []
    cutoff = time.time() - 86400
    calls = []
    for fpath in glob.glob(f'{cache_dir}/*.json'):
        try:
            mtime = os.path.getmtime(fpath)
            if mtime < cutoff: continue
            with open(fpath) as f:
                data = json.load(f)
            calls.append({'ts': mtime, 'file': os.path.basename(fpath), 'preview': data.get('response', '')[:100]})
        except: pass
    return calls

def read_cron_logs():
    """Lit les logs cron récents"""
    log_dir = f'{BASE_DIR}/manager'
    logs = []
    for pattern in ['cron_*.out.log', 'cron_*.err.log']:
        for fpath in glob.glob(f'{log_dir}/{pattern}'):
            try:
                mtime = os.path.getmtime(fpath)
                if mtime < time.time() - 172800: continue  # 2j
                with open(fpath, 'rb') as f:
                    f.seek(-2000, 2)  # fin du fichier
                    tail = f.read().decode('utf-8', errors='ignore').split('\n')[-20:]
                logs.append({'name': os.path.basename(fpath), 'tail': tail, 'mtime': mtime})
            except: pass
    return logs

def read_djemaly_builds():
    builds = []
    build_dir = f'{BASE_DIR}/state/djemaly_stories'
    for d in sorted(glob.glob(f'{build_dir}/*'), key=os.path.getmtime, reverse=True)[:5]:
        log = f'{d}/build.log'
        if os.path.exists(log):
            with open(log, 'rb') as f:
                f.seek(-1000, 2)
                tail = f.read().decode('utf-8', errors='ignore').split('\n')[-10:]
            builds.append({'dir': os.path.basename(d), 'tail': tail})
    return builds

# ── ENDPOINTS ──

@app.route('/api/v1/health')
def health():
    return jsonify({'status': 'ok', 'ts': datetime.utcnow().isoformat()})

@app.route('/api/v1/agents')
def agents():
    local = []
    for name, pattern, port in AGENTS_LOC:
        local.append(process_status(name, pattern, port))

    sb_agents = sb_get('agence_agent_health', 'limit=50')
    if isinstance(sb_agents, list):
        for a in sb_agents:
            existing = next((l for l in local if l['name'] == a.get('agent_name')), None)
            if existing:
                existing.update({'sb_status': a.get('status'), 'runs_24h': a.get('runs_24h', 0), 'fails_24h': a.get('fails_24h', 0)})
            else:
                local.append({'name': a.get('agent_name', 'unknown'), 'status': a.get('status', 'unknown'), 'runs_24h': a.get('runs_24h', 0), 'fails_24h': a.get('fails_24h', 0), 'last_ping': a.get('last_ping'), 'source': 'supabase'})

    # Ajouter agents distants (connus par leur présence dans Supabase runs)
    runs = sb_get('agence_runs', 'order=timestamp.desc&limit=200')
    if isinstance(runs, list):
        agents_in_runs = set()
        for r in runs:
            agent = r.get('agent', r.get('name'))
            if agent: agents_in_runs.add(agent)
        for agent_name in agents_in_runs:
            if not any(l['name'] == agent_name for l in local):
                agent_runs = [r for r in runs if r.get('agent') == agent_name or r.get('name') == agent_name]
                last_run = max((r.get('timestamp', '') for r in agent_runs), default='')
                status = 'healthy' if last_run and last_run > (datetime.utcnow() - timedelta(hours=1)).isoformat() else 'stale'
                local.append({'name': agent_name, 'status': status, 'runs_24h': len(agent_runs), 'source': 'supabase_runs', 'last_run': last_run})

    return jsonify({'agents': local, 'count': len(local), 'healthy': sum(1 for a in local if a.get('status') == 'healthy')})

@app.route('/api/v1/runs')
def runs():
    data = sb_get('agence_runs', 'order=timestamp.desc&limit=100')
    return jsonify({'runs': data if isinstance(data, list) else [], 'count': len(data) if isinstance(data, list) else 0})

@app.route('/api/v1/llm-costs')
def llm_costs():
    costs = sb_get('agence_llm_costs', 'order=ts.desc&limit=100')
    if isinstance(costs, list) and costs:
        total_24h = sum(c.get('cost_usd', 0) for c in costs if c.get('ts') and c['ts'] > (datetime.utcnow() - timedelta(hours=24)).isoformat())
        return jsonify({'total_24h': round(total_24h, 4), 'models': costs[:20], 'source': 'supabase'})

    # Estimation depuis proxy_cache
    proxy_calls = read_proxy_calls_24h()
    total = len(proxy_calls) * 0.015  # ~1.5c par appel pipeline
    models = {'pipeline_v9': {'calls': len(proxy_calls), 'cost_usd': round(total, 4)}}
    return jsonify({'total_24h': round(total, 4), 'models': [{'model': k, **v} for k, v in models.items()], 'source': 'estimated_from_proxy_cache'})

@app.route('/api/v1/providers')
def providers():
    ph = read_provider_health()
    return jsonify(ph)

@app.route('/api/v1/infra')
def infra():
    services = []
    try:
        r = requests.get(f'{PROXY_URL}/health', timeout=3)
        services.append({'name': 'Proxy Stéphane', 'status': 'online', 'latency_ms': int(r.elapsed.total_seconds()*1000)})
    except: services.append({'name': 'Proxy Stéphane', 'status': 'offline'})

    try:
        r = requests.get(f'{N8N_URL}/healthz', timeout=3)
        services.append({'name': 'n8n', 'status': 'online' if r.status_code == 200 else 'offline'})
    except: services.append({'name': 'n8n', 'status': 'offline'})

    try:
        r = requests.get(f'{SUPABASE_URL}/rest/v1/agence_runs?limit=1', headers=SB_HEADERS, timeout=5)
        services.append({'name': 'Supabase', 'status': 'online' if r.status_code == 200 else 'degraded'})
    except: services.append({'name': 'Supabase', 'status': 'offline'})

    # Webhook media
    try:
        r = requests.get('http://localhost:8790', timeout=2)
        services.append({'name': 'Webhook Media', 'status': 'online'})
    except: services.append({'name': 'Webhook Media', 'status': 'offline'})

    services.append({'name': 'Bright Data', 'status': 'online'})
    services.append({'name': 'ManyChat Bridge', 'status': 'offline', 'note': 'Non configuré'})
    services.append({'name': 'Phoenix Traces', 'status': 'offline', 'note': 'Non déployé'})

    return jsonify({'services': services, 'all_ok': all(s['status'] == 'online' for s in services)})

@app.route('/api/v1/alerts')
def alerts():
    data = sb_get('agence_alerts', 'order=ts.desc&limit=30')
    if isinstance(data, list) and data:
        return jsonify({'alerts': data, 'source': 'supabase'})

    alerts = []
    # Alerts depuis provider_health
    ph = read_provider_health()
    for model, info in ph.get('providers', {}).items():
        if info.get('status') == 'degraded':
            alerts.append({'ts': info.get('last_check', datetime.utcnow().isoformat()), 'agent': 'PROVIDER', 'severity': 'warn', 'message': f"{model} degraded — fail rate 1h: {info.get('fail_rate_1h', '?')}%"})
        if info.get('status') == 'dead':
            alerts.append({'ts': info.get('last_check', datetime.utcnow().isoformat()), 'agent': 'PROVIDER', 'severity': 'crit', 'message': f"{model} DOWN — {info.get('errors_24h', '?')} errors 24h"})

    # Alerts depuis agents
    agents_data = agents().json
    for a in agents_data['agents']:
        if a.get('status') == 'dead':
            alerts.append({'ts': datetime.utcnow().isoformat(), 'agent': a['name'], 'severity': 'crit', 'message': f"Agent {a['name']} dead — pas de processus détecté"})
        elif a.get('status') == 'stale':
            alerts.append({'ts': datetime.utcnow().isoformat(), 'agent': a['name'], 'severity': 'warn', 'message': f"Agent {a['name']} stale — réponse lente"})

    # Alert coût
    costs = llm_costs().json
    if costs.get('total_24h', 0) > 50:
        alerts.append({'ts': datetime.utcnow().isoformat(), 'agent': 'BUDGET', 'severity': 'warn', 'message': f"Coût LLM 24h: ${costs['total_24h']:.2f} — approche cap $80"})

    return jsonify({'alerts': alerts, 'source': 'generated', 'note': 'Table agence_alerts absente'})

@app.route('/api/v1/basile')
def basile():
    conv = sb_get('basile_conversations', 'limit=1')
    if isinstance(conv, list) and conv:
        return jsonify({'status': 'connected', 'conversations_24h': len(sb_get('basile_conversations', f"last_msg_at=gte.{(datetime.utcnow()-timedelta(hours=24)).isoformat()}") or []), 'total_conversations': len(conv), 'objections': sb_get('basile_objections', 'limit=5') or []})
    # Lire scraped basile intel
    intel_files = sorted(glob.glob(f'{BASE_DIR}/scraped/basile_intel/*.log'), key=os.path.getmtime, reverse=True)
    intel = []
    if intel_files:
        with open(intel_files[0], 'rb') as f:
            f.seek(-3000, 2)
            lines = f.read().decode('utf-8', errors='ignore').split('\n')[-30:]
        intel = lines
    return jsonify({'status': 'not_configured', 'intel_log': intel, 'note': 'Tables basile_* non créées. ManyChat webhook non branché. Scraping manuel actif.'})

@app.route('/api/v1/content')
def content():
    drafts = sb_get('agence_content_drafts', 'order=scheduled_for.asc&limit=20')
    return jsonify({'drafts': drafts if isinstance(drafts, list) else [], 'source': 'supabase' if isinstance(drafts, list) else 'none'})

@app.route('/api/v1/competitors')
def competitors():
    intel = sb_get('agence_competitor_intel', 'order=ts.desc&limit=20')
    return jsonify({'intel': intel if isinstance(intel, list) else [], 'source': 'supabase' if isinstance(intel, list) else 'none'})

@app.route('/api/v1/veille')
def veille():
    msgs = sb_get('agence_veille_messages', 'order=scraped_at.desc&limit=50')
    vids = sb_get('agence_veille_videos', 'order=scraped_at.desc&limit=50')
    return jsonify({'messages': msgs if isinstance(msgs, list) else [], 'videos': vids if isinstance(vids, list) else [], 'source': 'supabase'})

@app.route('/api/v1/djemaly')
def djemaly():
    stories = sb_get('djemaly_stories_daily', 'order=created_at.desc&limit=30')
    builds = read_djemaly_builds()
    return jsonify({'stories': stories if isinstance(stories, list) else [], 'builds': builds})

@app.route('/api/v1/cron-logs')
def cron_logs():
    return jsonify({'logs': read_cron_logs()})

@app.route('/api/v1/kpis')
def kpis():
    agents_data = agents().json
    runs_data = runs().json
    costs_data = llm_costs().json
    infra_data = infra().json
    providers_data = providers().json
    alerts_data = alerts().json

    # Runs 24h
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    runs_24h = [r for r in runs_data.get('runs', []) if r.get('timestamp', '') > cutoff]

    return jsonify({
        'agents': {
            'total': agents_data['count'],
            'healthy': agents_data['healthy'],
            'stale': sum(1 for a in agents_data['agents'] if a.get('status') == 'stale'),
            'dead': sum(1 for a in agents_data['agents'] if a.get('status') == 'dead'),
            'list': agents_data['agents']
        },
        'runs': {'total_24h': len(runs_24h), 'latest': runs_data.get('runs', [])[:10]},
        'llm': costs_data,
        'infra': infra_data,
        'providers': providers_data,
        'alerts': alerts_data,
        'ts': datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    print(f"[ADELLE API] Démarrage sur http://localhost:8765")
    print(f"[ADELLE API] Supabase: {SUPABASE_URL[:40]}...")
    app.run(host='0.0.0.0', port=8766, debug=False)
