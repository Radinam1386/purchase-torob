FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_STANDALONE=1 AGENT_API_INTERNAL=http://127.0.0.1:8000
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=web /web/.next/standalone ./web
COPY --from=web /web/.next/static ./web/.next/static
COPY --from=web /web/public ./web/public
COPY src ./src
COPY prompts ./prompts
COPY seed/catalog.sqlite.gz ./seed/catalog.sqlite.gz
COPY deploy/liara/start.py ./deploy/liara/start.py
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data /app/logs && chown -R app:app /app
EXPOSE 3000
CMD ["python", "deploy/liara/start.py"]
