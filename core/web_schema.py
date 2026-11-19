"""Web 端业务表建表与 RLS 语句（Supabase）。

本项目不保留 .sql 文件（``scripts/quality_gate.py --check-no-sql`` 会拦），且 Supabase
Python SDK 走 REST 不支持 DDL，故 schema 以本模块的常量形式版本化，由
``scripts/print_web_schema_ddl.py`` 打印后人工在 Supabase SQL Editor 执行一次。

覆盖 Web 应用直接读写的 19 张表：

- 用户配置：``user_settings``
- 会员：``planet_members``
- 持仓：``portfolios``、``portfolio_positions``（写策略另见
  ``core.portfolio_rls_membership``，本模块会一并拼进输出）
- 埋点：``user_activity_events``、``user_daily_activity``、``analytics_excluded_users``
- 行情信号：``market_signal_daily``
- 漏斗信号：``signal_pending``
- 归因：``strategy_attribution_reports``
- 推荐跟踪：``recommendation_tracking`` / ``_us`` / ``_hk``
- 影子账本：``shadow_account``、``shadow_positions``、``shadow_events``、
  ``shadow_nav_daily``、``shadow_trade_plans``

列集来源：

- Web 读取侧：``web/apps/web/src`` 与 ``web/apps/api/src`` 的 ``.from()`` 调用
- Python 写入侧：``core/recommendation_payload.py``、``core/candidate_metadata.py``、
  ``integrations/supabase_market_signal.py``、``core/shadow_ledger_schema.py``
  （影子账本表以该模块为准，本模块不重复定义）

全部语句幂等：``create table if not exists``、``drop policy if exists`` + ``create policy``，
可以重复执行。
"""

from __future__ import annotations

from core.portfolio_rls_membership import build_portfolio_write_rls_ddl

# 公共只读的市场数据表：匿名（未登录）与登录用户都可读。
PUBLIC_READ_TABLES: tuple[str, ...] = (
    "market_signal_daily",
    "signal_pending",
    "strategy_attribution_reports",
    "recommendation_tracking",
    "recommendation_tracking_us",
    "recommendation_tracking_hk",
)

# 影子账本只允许服务端（service_role）访问：启用 RLS 但不建任何策略。
SERVICE_ONLY_TABLES: tuple[str, ...] = (
    "shadow_account",
    "shadow_positions",
    "shadow_events",
    "shadow_nav_daily",
    "shadow_trade_plans",
)

TABLE_DDL: tuple[tuple[str, str], ...] = (
    (
        "user_settings",
        """create table if not exists public.user_settings (
  user_id text primary key,
  chat_provider text not null default '1route',
  gemini_api_key text not null default '',
  gemini_model text not null default '',
  gemini_base_url text not null default '',
  openai_api_key text not null default '',
  openai_model text not null default '',
  openai_base_url text not null default '',
  deepseek_api_key text not null default '',
  deepseek_model text not null default '',
  deepseek_base_url text not null default '',
  anthropic_api_key text not null default '',
  anthropic_model text not null default '',
  anthropic_base_url text not null default '',
  custom_providers jsonb not null default '{}'::jsonb,
  tushare_token text not null default '',
  feishu_webhook text not null default '',
  wecom_webhook text not null default '',
  dingtalk_webhook text not null default '',
  tg_bot_token text not null default '',
  tg_chat_id text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)""",
    ),
    (
        "planet_members",
        """create table if not exists public.planet_members (
  user_id text primary key,
  expires_on date,
  created_at timestamptz not null default now()
)""",
    ),
    (
        "portfolios",
        """create table if not exists public.portfolios (
  portfolio_id text primary key,
  free_cash numeric not null default 0,
  total_equity numeric,
  valued_at timestamptz,
  updated_at timestamptz not null default now()
)""",
    ),
    (
        "portfolio_positions",
        """create table if not exists public.portfolio_positions (
  portfolio_id text not null,
  code text not null,
  name text not null default '',
  shares integer not null default 0,
  cost_price numeric not null default 0,
  buy_dt date,
  stop_loss numeric,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (portfolio_id, code)
)""",
    ),
    (
        "user_activity_events",
        """create table if not exists public.user_activity_events (
  id bigint generated always as identity primary key,
  event_id text not null unique,
  user_id text not null,
  source text not null default 'web',
  session_id text,
  event_name text not null default 'page_view',
  feature text,
  route text,
  success boolean not null default true,
  duration_ms integer,
  app_version text,
  metadata jsonb not null default '{}'::jsonb,
  client_ts timestamptz,
  created_at timestamptz not null default now()
)""",
    ),
    (
        "user_daily_activity",
        """create table if not exists public.user_daily_activity (
  activity_date date not null,
  user_id text not null,
  sources text[] not null default '{}',
  event_count integer not null default 0,
  session_count integer not null default 0,
  feature_counts jsonb not null default '{}'::jsonb,
  first_seen_at timestamptz,
  last_seen_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (activity_date, user_id)
)""",
    ),
    (
        "analytics_excluded_users",
        """create table if not exists public.analytics_excluded_users (
  user_id text primary key,
  created_at timestamptz not null default now()
)""",
    ),
    (
        "market_signal_daily",
        """create table if not exists public.market_signal_daily (
  trade_date date primary key,
  benchmark_regime text,
  main_index_code text,
  main_index_close numeric,
  main_index_ma50 numeric,
  main_index_ma200 numeric,
  main_index_recent3_cum_pct numeric,
  main_index_today_pct numeric,
  smallcap_index_code text,
  smallcap_close numeric,
  smallcap_recent3_cum_pct numeric,
  premarket_regime text,
  premarket_reasons jsonb,
  a50_value_date date,
  a50_source text,
  a50_close numeric,
  a50_pct_chg numeric,
  vix_value_date date,
  vix_source text,
  vix_close numeric,
  vix_pct_chg numeric,
  banner_title text,
  banner_message text,
  banner_tone text,
  benchmark_slot jsonb,
  premarket_slot jsonb,
  market_posture_code text,
  market_posture_name text,
  wind_phrase text,
  water_phrase text,
  action_phrase text,
  source_jobs jsonb not null default '{}'::jsonb,
  data_json jsonb,
  updated_at timestamptz not null default now()
)""",
    ),
    (
        "signal_pending",
        """create table if not exists public.signal_pending (
  id bigint generated always as identity primary key,
  code bigint not null,
  name text not null default '',
  signal_type text not null,
  signal_date date not null,
  status text not null default 'pending',
  signal_score numeric not null default 0,
  days_elapsed integer not null default 0,
  regime text not null default '',
  industry text not null default '',
  snap_close numeric,
  snap_support numeric,
  snap_ma20 numeric,
  strategy_version text not null default '',
  candidate_lane text not null default '',
  entry_type text not null default '',
  signal_key text not null default '',
  candidate_status text not null default '',
  candidate_timing text not null default '',
  candidate_risk text not null default '',
  candidate_reasons jsonb,
  candidate_metrics jsonb,
  candidate_theme text,
  candidate_phase text,
  candidate_role text,
  mainline_score numeric,
  theme_score numeric,
  stock_role_score numeric,
  quality_score numeric,
  timing_score numeric,
  action_status text,
  action_label text,
  action_level text,
  direct_buy_allowed boolean,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)""",
    ),
    (
        "signal_pending_active_unique",
        """create unique index if not exists uq_signal_pending_active
  on public.signal_pending (code, signal_type)
  where status in ('pending', 'survived')""",
    ),
    (
        "strategy_attribution_reports",
        """create table if not exists public.strategy_attribution_reports (
  report_date date not null,
  market text not null default 'cn',
  window_start date,
  window_end date,
  horizons jsonb,
  signal_stats_json jsonb,
  score_bucket_stats_json jsonb,
  shadow_diff_stats_json jsonb,
  top_winners_json jsonb,
  top_losers_json jsonb,
  recommendations_json jsonb,
  signal_context_stats_json jsonb,
  created_at timestamptz not null default now(),
  primary key (report_date, market)
)""",
    ),
)

# 三张推荐跟踪表的列集完全一致，与 integrations/recommendation_payload.py 的
# RECOMMENDATION_BACKUP_COLUMNS + RECOMMENDATION_ATTRIBUTION_COLUMNS 对齐；
# on_conflict 键为 (code, recommend_date)。
_RECOMMENDATION_COLUMNS = """  code bigint not null,
  name text not null default '',
  recommend_reason text not null default '',
  recommend_date integer not null,
  initial_price numeric not null default 0,
  current_price numeric not null default 0,
  change_pct numeric not null default 0,
  recommend_count integer not null default 1,
  funnel_score numeric,
  is_ai_recommended boolean not null default false,
  rag_vetoed boolean not null default false,
  mfe_pct numeric,
  mae_pct numeric,
  range_amp_pct numeric,
  mfe_price numeric,
  mae_price numeric,
  performance_days integer,
  since_first_pct numeric,
  primary_signal text,
  signal_types text[],
  signal_track text,
  market_regime text,
  selection_source text,
  selection_rank integer,
  selection_is_fill boolean not null default false,
  priority_score numeric,
  trigger_score numeric,
  stage text,
  industry text,
  sector_state_code text,
  sector_state text,
  sector_note text,
  sector_guidance text,
  exit_signal text,
  exit_price numeric,
  exit_reason text,
  strategic_theme text,
  strategic_theme_score numeric,
  strategic_stock_score numeric,
  strategic_theme_state text,
  strategic_theme_bonus numeric,
  capital_migration_bonus numeric,
  springboard_a boolean,
  springboard_b boolean,
  springboard_c boolean,
  springboard_combo text,
  springboard_grade text,
  springboard_met_count integer,
  springboard_support text,
  springboard_touch_count integer,
  springboard_evidence text,
  springboard_scored boolean,
  strategy_version text,
  candidate_lane text,
  entry_type text,
  signal_key text,
  candidate_status text,
  candidate_timing text,
  candidate_risk text,
  candidate_reasons jsonb,
  candidate_metrics jsonb,
  candidate_theme text,
  candidate_phase text,
  candidate_role text,
  mainline_score numeric,
  theme_score numeric,
  stock_role_score numeric,
  quality_score numeric,
  timing_score numeric,
  dynamic_shadow_score numeric,
  dynamic_shadow_promotion jsonb,
  action_status text,
  action_label text,
  action_level text,
  direct_buy_allowed boolean,
  signal_type text,
  updated_at timestamptz not null default now(),
  primary key (code, recommend_date)
"""

RECOMMENDATION_TABLES: tuple[str, ...] = (
    "recommendation_tracking",
    "recommendation_tracking_us",
    "recommendation_tracking_hk",
)

_ACTIVE_MEMBER = """exists (
    select 1
    from public.planet_members pm
    where pm.user_id = auth.uid()::text
      and (pm.expires_on is null or pm.expires_on >= (timezone('Asia/Shanghai', now()))::date)
  )"""


def _policy(
    name: str, table: str, cmd: str, using: str | None = None, check: str | None = None, roles: str = "authenticated"
) -> str:
    clause = f" to {roles}"
    if using:
        clause += f" using ({using})"
    if check:
        clause += f" with check ({check})"
    return f"drop policy if exists {name} on public.{table};\ncreate policy {name} on public.{table} for {cmd}{clause}"


def _rls_ddl() -> str:
    blocks: list[str] = []

    blocks.append("alter table public.user_settings enable row level security")
    blocks.append(_policy("user_settings_select_own", "user_settings", "select", using="user_id = auth.uid()::text"))
    blocks.append(_policy("user_settings_insert_own", "user_settings", "insert", check="user_id = auth.uid()::text"))
    blocks.append(
        _policy(
            "user_settings_update_own",
            "user_settings",
            "update",
            using="user_id = auth.uid()::text",
            check="user_id = auth.uid()::text",
        )
    )

    blocks.append("alter table public.planet_members enable row level security")
    blocks.append(_policy("planet_members_select_own", "planet_members", "select", using="user_id = auth.uid()::text"))

    blocks.append("alter table public.user_activity_events enable row level security")
    blocks.append(
        _policy("user_activity_events_select_own", "user_activity_events", "select", using="user_id = auth.uid()::text")
    )
    blocks.append(
        _policy("user_activity_events_insert_own", "user_activity_events", "insert", check="user_id = auth.uid()::text")
    )

    blocks.append("alter table public.user_daily_activity enable row level security")
    blocks.append(
        _policy("user_daily_activity_select_own", "user_daily_activity", "select", using="user_id = auth.uid()::text")
    )
    blocks.append(
        _policy("user_daily_activity_insert_own", "user_daily_activity", "insert", check="user_id = auth.uid()::text")
    )
    blocks.append(
        _policy(
            "user_daily_activity_update_own",
            "user_daily_activity",
            "update",
            using="user_id = auth.uid()::text",
            check="user_id = auth.uid()::text",
        )
    )

    blocks.append("alter table public.analytics_excluded_users enable row level security")
    blocks.append(
        _policy(
            "analytics_excluded_users_select_own",
            "analytics_excluded_users",
            "select",
            using="user_id = auth.uid()::text",
        )
    )

    for table in PUBLIC_READ_TABLES:
        blocks.append(f"alter table public.{table} enable row level security")
        blocks.append(_policy(f"{table}_public_read", table, "select", using="true", roles="anon, authenticated"))

    for table in SERVICE_ONLY_TABLES:
        blocks.append(f"alter table public.{table} enable row level security")

    return "\n\n".join(blocks)


def build_ddl() -> str:
    """幂等 DDL：建表 + 唯一索引 + RLS。可重复执行，不会覆盖已有数据。"""
    parts: list[str] = [
        "-- Web 端业务表。由 core/web_schema.py 生成，请勿手改；改 schema 请改那个模块。",
        "-- 幂等：create table if not exists / drop policy if exists + create policy。",
        "",
    ]
    for _name, ddl in TABLE_DDL:
        parts.append(ddl.rstrip() + ";")
        parts.append("")
    for table in RECOMMENDATION_TABLES:
        parts.append(f"create table if not exists public.{table} (\n{_RECOMMENDATION_COLUMNS});")
        parts.append("")
    parts.append("-- RLS")
    parts.append(_rls_ddl())
    parts.append("")
    parts.append("-- 持仓写策略：本人 + 有效星球会员（core/portfolio_rls_membership.py）")
    parts.append(build_portfolio_write_rls_ddl().rstrip())
    return "\n".join(parts) + "\n"


def table_names() -> tuple[str, ...]:
    names = [name for name, _ in TABLE_DDL if not name.endswith("_unique")]
    return (*names, *RECOMMENDATION_TABLES)
