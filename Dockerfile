FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wsgi.py .
COPY app ./app

RUN mkdir -p /data

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1/healthz')"

CMD ["gunicorn", "--preload", "--bind", "0.0.0.0:80", "--workers", "2", "--threads", "4", "--timeout", "60", "wsgi:app"]
