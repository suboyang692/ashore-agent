"""研岸：MySQL 连接与查询封装。"""
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app.config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def get_conn():
    """返回一个新的数据库连接（DictCursor：查询结果即字典）。"""
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
    )


@contextmanager
def conn_ctx():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql, args=None):
    with conn_ctx() as conn, conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()


def query_one(sql, args=None):
    rows = query_all(sql, args)
    return rows[0] if rows else None


def execute(sql, args=None):
    """执行写操作，返回自增 id（无则返回受影响行数）。"""
    with conn_ctx() as conn, conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.lastrowid or cur.rowcount
