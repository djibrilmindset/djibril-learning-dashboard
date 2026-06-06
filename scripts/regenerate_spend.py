#!/usr/bin/env python3
"""Regenerate llm-spend.json and llm-spend-raw.json from hermes_llm_calls.jsonl"""
import json, os, sys, glob
from datetime import datetime, timezone, timedelta
from collections import defaultdict

BASE = os.path.expanduser('~')
JSONL_PATH = f'{BASE}/agence-ia/logs/hermes_llm_calls.jsonl'
DATA_DIR = f'{BASE}/djibril-learning-dashboard/data'
NOW = datetime.now(timezone.utc)

# ── Read JSONL ──
def parse_jsonl_line(line):
    """Safe JSON parser that handles bare decimal points like .018952 (invalid in strict JSON)."""
    s = line.strip()
    if not s:
        return None
    # Fix bare decimal points: `.number` -> `0.number`
    import re
    s = re.sub(r':\s*\.(\d+)', r': 0.\1', s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None

entries = []
if os.path.exists(JSONL_PATH):
    with open(JSONL_PATH) as f:
        for line in f:
            entry = parse_jsonl_line(line)
            if entry:
                entries.append(entry)
else:
    # Fallback: try token_tracking.jsonl
    JSONL_PATH = f'{BASE}/agence-ia/state/token_tracking.jsonl'
    if os.path.exists(JSONL_PATH):
        with open(JSONL_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

print(f"Read {len(entries)} total entries from JSONL")

# ── 24h window for llm-spend.json ──
cutoff_24h = NOW - timedelta(hours=24)
recent = [e for e in entries if e.get('ts', '') >= cutoff_24h.strftime('%Y-%m-%dT%H:%M:%S') or
          (isinstance(e.get('ts'), (int, float)) and e['ts'] >= cutoff_24h.timestamp())]

if not recent:
    # Try parsing ISO timestamps properly
    recent = []
    for e in entries:
        ts = e.get('ts', '')
        if isinstance(ts, str):
            try:
                t = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if t >= cutoff_24h:
                    recent.append(e)
            except (ValueError, TypeError):
                pass

print(f"  {len(recent)} entries in last 24h")

# ── Aggregate by model ──
model_agg = defaultdict(lambda: {
    'calls': 0, 'successes': 0, 'errors': 0,
    'cost_usd': 0.0, 'tokens_in': 0, 'tokens_out': 0
})
providers_seen = set()
models_seen = set()

for e in recent:
    model = e.get('model', 'unknown')
    provider = model.split('/')[0] if '/' in model else 'unknown'
    cost = float(e.get('cost_usd', e.get('cost', 0)) or 0)
    ti = int(e.get('tokens_in', e.get('input_tokens', e.get('prompt_tokens', 0) or 0)))
    to = int(e.get('tokens_out', e.get('output_tokens', e.get('completion_tokens', 0) or 0)))
    
    model_agg[model]['calls'] += 1
    model_agg[model]['successes'] += 1
    model_agg[model]['cost_usd'] += cost
    model_agg[model]['tokens_in'] += ti
    model_agg[model]['tokens_out'] += to
    models_seen.add(model)
    providers_seen.add(provider)

# ── Build llm-spend.json ──
total_cost = sum(v['cost_usd'] for v in model_agg.values())
by_model = []
for model, agg in sorted(model_agg.items(), key=lambda x: -x[1]['cost_usd']):
    provider = model.split('/')[0] if '/' in model else 'unknown'
    by_model.append({
        'model': model,
        'provider': provider,
        'calls': agg['calls'],
        'successes': agg['successes'],
        'errors': agg['errors'],
        'cost_usd': round(agg['cost_usd'], 6),
        'tokens_in': agg['tokens_in'],
        'tokens_out': agg['tokens_out'],
        'status': 'healthy' if agg['errors'] == 0 else 'degraded',
        'price_in_per_1k': round(agg['cost_usd'] / max(agg['tokens_in'] / 1000, 0.001), 6) if agg['tokens_in'] > 0 else 0,
        'price_out_per_1k': round(agg['cost_usd'] / max(agg['tokens_out'] / 1000, 0.001), 6) if agg['tokens_out'] > 0 else 0,
    })

spend = {
    '_meta': {
        'generated_at': NOW.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'window_hours': 24,
        'total_calls': sum(v['calls'] for v in model_agg.values()),
        'total_cost_usd': round(total_cost, 4),
        'models_count': len(models_seen),
        'providers_count': len(providers_seen),
        'errors_count': sum(v['errors'] for v in model_agg.values()),
        'healthy_count': sum(1 for v in model_agg.values() if v['errors'] == 0),
        'error_count': sum(v['errors'] for v in model_agg.values()),
    },
    'by_model': by_model,
}

# ── Build llm-spend-raw.json (all entries, cumulative) ──
raw_entries = []
for e in entries:
    raw_entries.append({
        'ts': e.get('ts', ''),
        'agent': e.get('agent', e.get('agent_name', 'unknown')),
        'model': e.get('model', 'unknown'),
        'tier': e.get('tier', e.get('tier_level', 2)),
        'tokens_in': int(e.get('tokens_in', e.get('input_tokens', e.get('prompt_tokens', 0) or 0))),
        'tokens_out': int(e.get('tokens_out', e.get('output_tokens', e.get('completion_tokens', 0) or 0))),
        'cost_usd': float(e.get('cost_usd', e.get('cost', 0)) or 0),
        'task_type': e.get('task_type', e.get('type', 'unknown')),
        'result_summary': (e.get('result_summary', '') or '')[:100],
    })

all_models = set(e['model'] for e in raw_entries)
all_providers = set(e['model'].split('/')[0] if '/' in e['model'] else 'unknown' for e in raw_entries)

raw = {
    '_meta': {
        'generated_at': NOW.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'window_hours': 24,
        'total_calls': len(raw_entries),
        'total_cost_usd': round(sum(e['cost_usd'] for e in raw_entries), 6),
        'models_count': len(all_models),
        'providers_count': len(all_providers),
        'errors_count': 0,
        'healthy_count': len(raw_entries),
        'error_count': 0,
    },
    'entries': raw_entries,
}

# ── Write files ──
os.makedirs(DATA_DIR, exist_ok=True)

spend_path = f'{DATA_DIR}/llm-spend.json'
with open(spend_path, 'w') as f:
    json.dump(spend, f, indent=2, ensure_ascii=False)
print(f"Wrote {spend_path} ({os.path.getsize(spend_path)} bytes, {len(by_model)} models)")

raw_path = f'{DATA_DIR}/llm-spend-raw.json'
with open(raw_path, 'w') as f:
    json.dump(raw, f, indent=2, ensure_ascii=False)
print(f"Wrote {raw_path} ({os.path.getsize(raw_path)} bytes, {len(raw_entries)} entries)")

# ── Also update dashboard_brief_v2.json ──
brief_path = f'{DATA_DIR}/dashboard_brief_v2.json'
if os.path.exists(brief_path):
    with open(brief_path) as f:
        brief = json.load(f)
    brief['generated'] = NOW.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    brief['key_metrics'] = {
        'agents_total': brief.get('key_metrics', {}).get('agents_total', 24),
        'providers_online': len(providers_seen),
        'network_count': brief.get('key_metrics', {}).get('network_count', 10),
        'llm_calls_24h': spend['_meta']['total_calls'],
        'llm_cost_24h': spend['_meta']['total_cost_usd'],
    }
    with open(brief_path, 'w') as f:
        json.dump(brief, f)
    print(f"Updated {brief_path}")

print("\n✅ Done!")
