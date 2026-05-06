-- Migration 001: Création des tables manquantes pour le dashboard opérationnel
-- À exécuter dans Supabase SQL Editor

-- Table des coûts LLM réels (alimentée par le proxy)
create table if not exists agence_llm_costs (
  id bigserial primary key,
  ts timestamptz default now(),
  model text not null,
  agent text,
  provider text,
  tokens_in int,
  tokens_out int,
  cost_usd numeric(10,4),
  latency_ms int,
  status text default 'success' check (status in ('success', 'error', 'timeout'))
);
create index if not exists idx_llm_costs_ts on agence_llm_costs(ts desc);
create index if not exists idx_llm_costs_model on agence_llm_costs(model);

-- Table des alertes opérationnelles
create table if not exists agence_alerts (
  id bigserial primary key,
  ts timestamptz default now(),
  agent text,
  severity text check (severity in ('crit','warn','info')),
  message text not null,
  acknowledged boolean default false
);
create index if not exists idx_alerts_ts on agence_alerts(ts desc);
create index if not exists idx_alerts_severity on agence_alerts(severity);

-- Table KPIs agrégés pour le dashboard
create table if not exists dashboard_kpis (
  id bigserial primary key,
  ts timestamptz default now(),
  category text not null,
  metric_name text not null,
  metric_value numeric(12,4),
  metric_text text,
  agent text,
  source text
);
create index if not exists idx_kpis_ts on dashboard_kpis(ts desc);
create index if not exists idx_kpis_category on dashboard_kpis(category);

-- Table contenu / calendrier éditorial
create table if not exists agence_content_drafts (
  id bigserial primary key,
  title text,
  category text,
  status text default 'draft' check (status in ('draft','review','scheduled','published','archived')),
  tags text[],
  agent text,
  scheduled_for timestamptz,
  created_at timestamptz default now(),
  published_at timestamptz
);

-- Table veille messages (10 réseaux)
create table if not exists agence_veille_messages (
  id bigserial primary key,
  network text,
  who text,
  text text,
  engagement int,
  sentiment text,
  tags text[],
  url text,
  scraped_at timestamptz default now()
);
create index if not exists idx_veille_msg_scraped on agence_veille_messages(scraped_at desc);

-- Table veille vidéos
create table if not exists agence_veille_videos (
  id bigserial primary key,
  network text,
  who text,
  title text,
  duration_sec int,
  views bigint,
  engagement_pct numeric(4,1),
  hook_analysis text,
  thumbnail_url text,
  url text,
  scraped_at timestamptz default now()
);

-- Table formats viraux
create table if not exists agence_viral_formats (
  id bigserial primary key,
  network text,
  format_name text,
  description text,
  score int check (score between 0 and 100),
  volume_7d int,
  example text,
  last_updated timestamptz default now()
);

-- Table concurrents
create table if not exists agence_competitor_intel (
  id bigserial primary key,
  who text,
  signal_type text,
  threat_level text check (threat_level in ('high','med','low')),
  summary text,
  tags text[],
  url text,
  ts timestamptz default now()
);

-- Table leads / pipeline commercial
create table if not exists agence_leads_scored (
  id bigserial primary key,
  ig_handle text,
  source text,
  score int check (score between 0 and 100),
  intent text,
  status text default 'new',
  level int,
  last_action_at timestamptz
);

-- Table Instagram metrics
create table if not exists agence_ig_metrics (
  id bigserial primary key,
  handle text,
  followers int,
  following int,
  posts int,
  engagement_rate numeric(4,2),
  avg_likes int,
  avg_comments int,
  scraped_at timestamptz default now()
);

-- Tables Basile (ManyChat bridge)
create table if not exists basile_conversations (
  id text primary key,
  ig_user text,
  opened_at timestamptz,
  last_msg_at timestamptz,
  status text,
  lead_score int,
  intent text,
  current_flow text
);

create table if not exists basile_messages (
  id bigserial primary key,
  conv_id text references basile_conversations(id),
  ts timestamptz,
  direction text check (direction in ('in','out')),
  text text,
  intent_detected text,
  ctr_if_link bool
);

create table if not exists basile_flows (
  id text primary key,
  name text,
  status text,
  msgs_24h int,
  drop_pct numeric(4,1),
  description text
);

create table if not exists basile_objections (
  objection_type text primary key,
  count int,
  resolved_count int,
  resolved_pct numeric(4,1)
);

create table if not exists basile_ai_sync (
  id bigserial primary key,
  ts timestamptz default now(),
  agent text,
  direction text,
  action text,
  state text
);

-- Enable Realtime sur les tables critiques
alter publication supabase_realtime add table agence_alerts;
alter publication supabase_realtime add table basile_ai_sync;
alter publication supabase_realtime add table dashboard_kpis;
