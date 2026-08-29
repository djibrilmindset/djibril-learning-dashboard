#!/usr/bin/env python3
"""Update llm-spend.json and llm-spend-raw.json from JSONL log."""
import json, datetime, os, sys

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
JSONL = os.path.expanduser('~/agence-ia/logs/hermes_llm_calls.jsonl')
now = datetime.datetime.utcnow()
cutoff = (now - datetime.timedelta(hours=24)).isoformat()

calls = []
try:
    with open(JSONL) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    calls.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
except FileNotFoundError:
    print("JSONL not found", file=sys.stderr)
    sys.exit(1)

if not calls:
    meta = {
        'generated_at': now.isoformat() + 'Z', 'window_hours': 24,
        'total_calls': 0, 'total_cost_usd': 0, 'models_count': 0,
        'providers_count': 0, 'errors_count': 0, 'healthy_count': 0, 'error_count': 0
    }
    for fn in ['llm-spend.json', 'llm-spend-raw.json']:
        with open(os.path.join(DATA_DIR, fn), 'w') as f:
            json.dump({'_meta': meta, 'by_model' if 'raw' not in fn else 'entries': []}, f, indent=2)
    print("0 calls, empty")
    sys.exit(0)

recent = [c for c in calls if c.get('ts', '').replace('Z', '') >= cutoff]
if not recent:
    cutoff_7d = (now - datetime.timedelta(days=7)).isoformat()
    recent = [c for c in calls if c.get('ts', '').replace('Z', '') >= cutoff_7d]

models = {}
for c in recent:
    m = c.get('model', 'unknown')
    if m not in models:
        prov = m.split('/')[0] if '/' in m else 'direct'
        models[m] = {'model': m, 'provider': prov, 'calls': 0, 'successes': 0,
                     'errors': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0}
    models[m]['calls'] += 1
    models[m]['successes'] += 1
    models[m]['tokens_in'] += c.get('tokens_in', 0)
    models[m]['tokens_out'] += c.get('tokens_out', 0)
    models[m]['cost_usd'] += c.get('cost_usd', 0)

tc = sum(m['cost_usd'] for m in models.values())
meta = {
    'generated_at': now.isoformat() + 'Z', 'window_hours': 24,
    'total_calls': len(recent), 'total_cost_usd': round(tc, 6),
    'models_count': len(models),
    'providers_count': len(set(m['provider'] for m in models.values())),
    'errors_count': 0, 'healthy_count': len(models), 'error_count': 0
}
llm = {'_meta': meta, 'by_model': sorted(models.values(), key=lambda x: x['cost_usd'], reverse=True)}
with open(os.path.join(DATA_DIR, 'llm-spend.json'), 'w') as f:
    json.dump(llm, f, indent=2)

raw_entries = [{
    'ts': c['ts'], 'agent': c.get('agent', ''), 'model': c.get('model', ''),
    'tier': c.get('tier', 0), 'tokens_in': c.get('tokens_in', 0),
    'tokens_out': c.get('tokens_out', 0), 'cost_usd': c.get('cost_usd', 0),
    'task_type': c.get('task_type', ''), 'result_summary': c.get('result_summary', '')
} for c in recent]
with open(os.path.join(DATA_DIR, 'llm-spend-raw.json'), 'w') as f:
    json.dump({'_meta': meta, 'entries': raw_entries}, f, indent=2)

print(f"{len(recent)} calls, {len(models)} models, ${tc:.4f}")
