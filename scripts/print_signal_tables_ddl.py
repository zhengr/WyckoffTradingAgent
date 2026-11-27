"""打印 signal_* 表的建表 DDL，供 Supabase SQL Editor 执行（幂等）。

用法::

    python scripts/print_signal_tables_ddl.py

注意：Postgres 不支持 ``create policy if not exists``，RLS 部分输出的是
DO 块幂等形式，直接整段贴进 SQL Editor 即可重复执行。
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

from core.signal_tables_schema import SIGNAL_TABLES_DDL, SIGNAL_TABLES_INDEXES, build_ddl


def main() -> int:
    print(build_ddl())
    print("")
    print("-- 索引")
    for stmt in SIGNAL_TABLES_INDEXES:
        print(stmt)
    print("")
    print("-- RLS（DO 块幂等，可重复执行）")
    names = [name for name, _ in SIGNAL_TABLES_DDL]
    print("do $$")
    print("begin")
    for name in names:
        print(f"  execute format('alter table public.%s enable row level security', '{name}');")
        print(
            f"  if not exists (select 1 from pg_policies where schemaname='public' and tablename='{name}' and policyname='public_read') then"
        )
        print(f"    create policy public_read on public.{name} for select to anon, authenticated using (true);")
        print("  end if;")
    print("end $$;")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
