"""补齐企业化基础表，兼容已有数据库。

用法：python db/migrate_enterprise.py
迁移可重复执行：schema.sql 中的建表语句均使用 IF NOT EXISTS；
同时补一个 default 用户，让现有 CLI 和旧接口继续可用。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql

from app.config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER
from db.init_db import _exec_statements


def main():
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        _exec_statements(conn, schema)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO users (id, username, role, status) VALUES (%s, %s, 'student', 'active')",
                ("default", "default"),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("[ok] 企业化基础表迁移完成")
    print("[ok] default 用户已就绪，旧 CLI/API 继续兼容")


if __name__ == "__main__":
    main()
