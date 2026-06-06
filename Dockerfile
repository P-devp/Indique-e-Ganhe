FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY backend/ backend/
COPY src/ src/
COPY *.html *.css run.py ./

# Production defaults
ENV PORT=5000
ENV FLASK_DEBUG=0
ENV DISABLE_SEED=1
ENV PUBLIC_AFFILIATES=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["python", "backend/app.py"]
