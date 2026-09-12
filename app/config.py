"""研岸 Ashore 配置：统一从 .env 读取。"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 大模型
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "ashore")

# Redis（检索结果缓存 + 多轮会话记忆；连不上会自动降级为进程内实现）
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() not in ("0", "false", "no")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_TIMEOUT = float(os.getenv("REDIS_TIMEOUT", "0.3"))   # 秒；探测不能拖慢首次请求
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))            # 检索结果缓存 1 小时
SESSION_TTL = int(os.getenv("SESSION_TTL", "86400"))       # 会话记忆 1 天
SESSION_MAX = int(os.getenv("SESSION_MAX", "20"))          # 每个用户最多保留多少条消息
