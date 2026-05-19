# ---- build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/
COPY babel.cfg .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir babel \
    && /opt/venv/bin/pybabel compile \
        -d src/uniqlo_sales_alerter/i18n/locale \
        -l en \
        -i src/uniqlo_sales_alerter/i18n/locale/en/LC_MESSAGES/messages.po \
    && /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime stage ----
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN useradd -r -u 1000 alerter \
    && mkdir -p /app/data \
    && chown -R alerter:alerter /app

USER alerter

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uniqlo_sales_alerter"]
