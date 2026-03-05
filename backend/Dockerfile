###############################################################################
# Stage 1: Compile Python dependencies (build-time only)
###############################################################################
FROM python:3.11-slim-bookworm AS python-deps

WORKDIR /deps

# Build-time libs needed to compile psycopg2, cryptography, and pango bindings
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libcairo2-dev \
    libpango1.0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --no-compile: skip .pyc generation (saves ~15 MB in site-packages)
# --no-cache-dir: don't store pip download cache
RUN pip install --no-cache-dir --no-compile --user -r requirements.txt \
    && find /root/.local -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null; true \
    && find /root/.local -name "tests" -type d -exec rm -rf {} + 2>/dev/null; true \
    && find /root/.local -name "test_*.py" -exec rm -f {} + 2>/dev/null; true \
    && find /root/.local -name "*.pyx" -exec rm -f {} + 2>/dev/null; true \
    && find /root/.local -name "doc" -type d -exec rm -rf {} + 2>/dev/null; true \
    && find /root/.local -name "docs" -type d -exec rm -rf {} + 2>/dev/null; true \
    && find /root/.local -name "examples" -type d -exec rm -rf {} + 2>/dev/null; true

###############################################################################
# Stage 2: Production image — lean, no compiler, no dev tools
###############################################################################
FROM python:3.11-slim-bookworm AS production

WORKDIR /app

# Runtime-only system libs. WeasyPrint 60.x needs Pango (via CFFI) but NOT Cairo directly.
# libpangocairo pulls in libcairo2 as a transitive dep — unavoidable.
# shared-mime-info omitted — WeasyPrint 60.x uses built-in MIME detection.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from Stage 1
COPY --from=python-deps /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . .

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]

###############################################################################
# Stage 3: Development image — production runtime + dev tools
###############################################################################
FROM python:3.11-slim-bookworm AS development

WORKDIR /app

# Runtime + build libs (all in one layer since we install packages from source here)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libpango1.0-dev \
    libffi-dev \
    libcairo2-dev \
    shared-mime-info \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.dev.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements.dev.txt

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
