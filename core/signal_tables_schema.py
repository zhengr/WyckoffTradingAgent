"""signal_* 表的版本化 schema（CI 自建 Supabase 时一次性建齐）。

本项目不保留 .sql 文件，schema 以本模块的常量形式版本化，
由 scripts/print_signal_tables_ddl.py 输出 DDL 供 Supabase SQL Editor 执行。

表用途（写入方全是 CI / service key，RLS 只放开 public read)：
- signal_observations:      每日漏斗信号观测（persist_step3_signal_observations 写入）
- signal_outcomes:          信号结算结果（signal_feedback_job 写入）
- signal_health_daily:      信号健康度日统计
- signal_registry:          信号权重注册表（按 signal_type × regime)
- signal_policy_shadow_runs: 影子策略归因游程
"""

from __future__ import annotations

SIGNAL_TABLES_DDL: tuple[tuple[str, str], ...] = (
    (
        "signal_observations",
        """
create table if not exists public.signal_observations (
  id bigint generated always as identity primary key,
  market text not null default 'cn',
  trade_date date not null,
  code text not null,
  signal_type text not null,
  name text default '',
  track text default '',
  regime text default 'NEUTRAL',
  industry text default '',
  stage text default '',
  channel text default '',
  profile_tag text default '',
  stage_tag text default '',
  trigger_tags text[] default '{}',
  selection_mode text default '',
  policy_version text default '',
  candidate_rank integer,
  trigger_score double precision,
  priority_score double precision,
  entry_price double precision default 0,
  selected_for_ai boolean default false,
  ai_recommended boolean default false,
  source text default 'funnel',
  strategy_version text,
  candidate_lane text,
  entry_type text,
  signal_key text,
  candidate_status text,
  lifecycle_status text default 'ACTIVE',
  features_json jsonb,
  springboard_grade text,
  springboard_met_count integer,
  springboard_a text,
  springboard_b text,
  springboard_c text,
  springboard_support text,
  springboard_touch_count integer,
  springboard_evidence jsonb,
  updated_at timestamptz default now(),
  unique (market, trade_date, code, signal_type)
)
""",
    ),
    (
        "signal_outcomes",
        """
create table if not exists public.signal_outcomes (
  id bigint generated always as identity primary key,
  observation_id bigint not null references public.signal_observations(id) on delete cascade,
  market text default 'cn',
  trade_date date,
  code text,
  signal_type text,
  track text,
  regime text,
  horizon_days integer not null,
  status text default 'pending',
  return_pct double precision,
  max_drawdown_pct double precision,
  updated_at timestamptz default now(),
  unique (observation_id, horizon_days)
)
""",
    ),
    (
        "signal_health_daily",
        """
create table if not exists public.signal_health_daily (
  id bigint generated always as identity primary key,
  market text not null default 'cn',
  as_of_date date not null,
  signal_type text not null,
  track text default '',
  regime text default 'ALL',
  horizon_days integer not null default 10,
  sample_count integer default 0,
  win_rate_pct double precision,
  avg_return_pct double precision,
  median_return_pct double precision,
  avg_drawdown_pct double precision,
  health_state text default 'INSUFFICIENT',
  weight_multiplier double precision default 1.0,
  reason text default '',
  updated_at timestamptz default now(),
  unique (market, as_of_date, signal_type, track, regime, horizon_days)
)
""",
    ),
    (
        "signal_registry",
        """
create table if not exists public.signal_registry (
  id bigint generated always as identity primary key,
  market text not null default 'cn',
  signal_type text not null,
  track text default '',
  regime text default 'ALL',
  status text default 'ACTIVE',
  weight_multiplier double precision default 1.0,
  sample_count integer default 0,
  win_rate_pct double precision,
  avg_return_pct double precision,
  horizon_days integer not null default 10,
  reason text default '',
  updated_at timestamptz default now(),
  unique (market, signal_type, regime)
)
""",
    ),
    (
        "signal_policy_shadow_runs",
        """
create table if not exists public.signal_policy_shadow_runs (
  id bigint generated always as identity primary key,
  run_date date,
  report_date text,
  market text default 'cn',
  base_policy jsonb,
  signal_weights jsonb,
  attribution_signal_weights jsonb,
  attribution_policy_meta jsonb,
  reason text,
  created_at timestamptz default now()
)
""",
    ),
)

SIGNAL_TABLES_INDEXES: tuple[str, ...] = (
    "create index if not exists signal_observations_trade_date_idx on public.signal_observations (trade_date desc);",
    "create index if not exists signal_outcomes_obs_idx on public.signal_outcomes (observation_id);",
)

SIGNAL_TABLES_RLS: tuple[str, ...] = (
    "alter table public.{t} enable row level security;",
    "create policy if not exists public_read on public.{t} for select to anon, authenticated using (true);",
)


def build_ddl() -> str:
    """输出建表 + 索引 DDL（幂等）。"""
    parts: list[str] = ["-- signal_* 表（CI 自建 Supabase 缺失时执行一次，幂等）", ""]
    for name, ddl in SIGNAL_TABLES_DDL:
        parts.append(f"-- {name}")
        parts.append(ddl.strip() + ";")
        parts.append("")
    parts.append("-- 索引")
    for stmt in SIGNAL_TABLES_INDEXES:
        parts.append(stmt)
    return "\n".join(parts)


def build_rls_ddl() -> str:
    """输出 RLS 启用 + public read 策略（Postgres 不支持 create policy if not exists，
    生产环境请用 DO 块幂等执行，见 scripts/print_signal_tables_ddl.py 输出说明）。"""
    parts: list[str] = ["-- RLS：启用行级安全，匿名只读，写入仅 service key（绕过 RLS）"]
    for name, _ in SIGNAL_TABLES_DDL:
        for stmt in SIGNAL_TABLES_RLS:
            parts.append(stmt.format(t=name))
    return "\n".join(parts)
