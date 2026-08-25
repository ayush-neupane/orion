# ============================================================
# ORION backend image
# Stage 1: deps      - install pinned requirements
# Stage 2: audit     - fail the build on known vulnerabilities
# Stage 3: runtime   - slim, non-root, healthchecked
# ============================================================
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS audit
RUN pip install --no-cache-dir pip-audit==2.7.3 \
    && pip-audit --strict -r requirements.txt \
    || (echo "SECURITY AUDIT FAILED: critical vulnerabilities detected" && exit 1)

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd -r orion && useradd -r -g orion orion \
    && mkdir -p /app/logs && chown -R orion:orion /app
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --chown=orion:orion app ./app
COPY --chown=orion:orion tests ./tests
USER orion
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]