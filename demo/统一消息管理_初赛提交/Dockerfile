FROM python:3.12-slim

WORKDIR /app

# 依赖单独一层，改代码时不用重装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV UMM_HOST=0.0.0.0 \
    UMM_MODE=mock \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else sys.exit(1)"

CMD ["python", "app.py"]
