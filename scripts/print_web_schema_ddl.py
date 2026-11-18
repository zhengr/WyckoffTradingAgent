"""打印 Web 端业务表建表与 RLS 语句，供人工在 Supabase SQL Editor 执行一次。

本项目不保留 .sql 文件，且 Supabase Python SDK 走 REST 不支持 DDL，故 schema 以
core/web_schema.py 的常量形式版本化并由此脚本输出。

输出包含 19 张表、唯一索引、RLS 策略，以及 core/portfolio_rls_membership.py 的持仓写策略。
全部语句幂等，可重复执行。

用法::

    python scripts/print_web_schema_ddl.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

from core.web_schema import build_ddl


def main() -> int:
    print(build_ddl())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
