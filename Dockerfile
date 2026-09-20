# 研岸 Ashore：应用镜像
#
#   docker compose up -d --build      一键起 app + mysql + redis
#   docker compose logs -f app        看日志
#
# 容器里跑的是 uvicorn 单进程；要多进程就加 --workers。会话记忆已经外置到 Redis，
# 加 worker 不会像进程内 dict 那样把上下文丢在另一个进程里（见 app/cache.py）。
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖再拷代码：只改业务代码时依赖层命中缓存，重建快很多
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY eval ./eval
COPY web ./web
COPY knowledge ./knowledge
COPY pytest.ini README.md ./

# data/ 下放的是 ChromaDB 向量库和 OCR 缓存，挂卷，容器重建不丢已入库的切片
VOLUME ["/app/data"]

EXPOSE 8000

# 用 /health 判断存活；start-period 给向量库冷启动留时间
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
