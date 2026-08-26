FROM node:22-alpine AS frontend-builder

WORKDIR /build/miniapp
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate

COPY miniapp/package.json miniapp/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY miniapp/ ./
RUN pnpm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 air \
    && useradd --uid 10001 --gid air --create-home --shell /usr/sbin/nologin air

COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN python -m pip install --no-cache-dir .

COPY --from=frontend-builder /build/miniapp/dist ./miniapp/dist

RUN mkdir -p /data /backups && chown air:air /data /backups

USER air
EXPOSE 8000

CMD ["python", "-m", "app.main"]
