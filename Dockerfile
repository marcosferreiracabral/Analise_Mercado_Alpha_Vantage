# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8501

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ ./app/
COPY README.md .env.example ./

# Create data directory
RUN mkdir -p /app/data

# Expose Streamlit port
EXPOSE 8501

# Healthcheck for container
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Default command starts the Streamlit dashboard
ENTRYPOINT ["streamlit", "run", "app/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
