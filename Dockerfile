FROM python:3.12-slim-bookworm AS telegram-api-builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake g++ make gperf libssl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --recursive https://github.com/tdlib/telegram-bot-api.git /src/telegram-bot-api
RUN cmake -S /src/telegram-bot-api -B /build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
RUN cmake --build /build --target install --parallel 2

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    TELEGRAM_API_BASE_URL=http://127.0.0.1:8081 \
    TELEGRAM_LOCAL_MODE=true
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libssl3 zlib1g libstdc++6 libgcc-s1 bash \
    && rm -rf /var/lib/apt/lists/*
COPY --from=telegram-api-builder /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt
COPY ai_service.py bot.py config.py session_store.py switch_to_local.py /app/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /data
VOLUME ["/data"]
ENTRYPOINT ["/app/entrypoint.sh"]
