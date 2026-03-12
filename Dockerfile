# Build Stage
FROM python:3.11-slim as builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install to a temp folder, then copy to global path
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final Stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime libs for OpenCV/OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages to global system path
COPY --from=builder /install /usr/local

# Setup App
COPY main.py .
COPY index.html .

# Create cache directories with correct permissions
RUN mkdir -p /app/.cache /app/data && chmod 777 /app/.cache /app/data
ENV HF_HOME=/app/.cache

# Create user
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]