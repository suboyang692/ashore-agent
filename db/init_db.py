"""研岸 D1：初始化 MySQL 数据库与四张核心表。
用法: python db/init_db.py    （先复制 .env.example 为 .env 并填好 MYSQL_PASSWORD）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql

from app.config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def _exec_statements(conn, sql_text: str) -> None:
    """逐条执行 schema.sql（按分号切分，跳过 -- 注释行）。"""
    buf = []
    with conn.cursor() as cur:
        for line in sql_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            buf.append(line)
            if stripped.endswith(";"):
                stmt = "\n".join(buf).strip().rstrip(";")
                buf = []
                if stmt:
                    cur.execute(stmt)
        if buf:
            stmt = "\n".join(buf).strip().rstrip(";")
            if stmt:
                cur.execute(stmt)


def main():
    if not MYSQL_PASSWORD or MYSQL_PASSWORD.startswith("在这里"):
        print("请先复制 .env.example 为 .env，并填入 MYSQL_PASSWORD（本机 MySQL root 密码）")
        sys.exit(1)

    # 1) 连接（不指定库）建库
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                           password=MYSQL_PASSWORD, charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB} "
                        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
        print(f"[ok] 数据库 {MYSQL_DB} 就绪")
    finally:
        conn.close()

    # 2) 执行 schema 建表
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    conn2 = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                            password=MYSQL_PASSWORD, database=MYSQL_DB, charset="utf8mb4")
    try:
        _exec_statements(conn2, schema_path.read_text(encoding="utf-8"))
        conn2.commit()
        print("[ok] 四张核心表已创建：questions / answer_records / user_mastery / eval_annotations")
        with conn2.cursor() as cur:
            cur.execute("SHOW TABLES")
            for row in cur.fetchall():
                print("   -", row[0])
    finally:
        conn2.close()


if __name__ == "__main__":
    main()
