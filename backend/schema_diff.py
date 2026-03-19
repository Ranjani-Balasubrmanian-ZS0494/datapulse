"""
schema_diff.py
--------------
Compares the column lists of the `sales` table between the source and target
Azure SQL databases using INFORMATION_SCHEMA.COLUMNS.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from config import settings


def get_schema_diff(
    source_conn: str | None = None,
    target_conn: str | None = None,
) -> dict:
    """
    Query both databases and return a structured column diff for the sales
    table.

    Parameters
    ----------
    source_conn : optional connection string override (for registered pipelines)
    target_conn : optional connection string override (for registered pipelines)

    Returns
    -------
    {
        "source_columns": [...],          # ordered list from source
        "target_columns": [...],          # ordered list from target
        "missing_in_source": [...],       # columns target has but source lacks
        "new_in_source": [...]            # columns source has that target lacks
    }
    """
    column_query = text(
        """
        SELECT COLUMN_NAME
        FROM   INFORMATION_SCHEMA.COLUMNS
        WHERE  TABLE_NAME = 'sales'
        ORDER  BY ORDINAL_POSITION
        """
    )

    src = source_conn or settings.SOURCE_DB_CONN
    tgt = target_conn or settings.TARGET_DB_CONN

    source_engine = create_engine(src)
    target_engine = create_engine(tgt)

    with source_engine.connect() as conn:
        source_columns: list[str] = [row[0] for row in conn.execute(column_query)]

    with target_engine.connect() as conn:
        target_columns: list[str] = [row[0] for row in conn.execute(column_query)]

    source_set = set(source_columns)
    target_set = set(target_columns)

    return {
        "source_columns": source_columns,
        "target_columns": target_columns,
        "missing_in_source": sorted(target_set - source_set),
        "new_in_source": sorted(source_set - target_set),
    }
