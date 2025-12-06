# Multi-stage Dockerfile for LinkedIn Reposter
# Supports both arm64 (M2 Mac) and amd64 (TrueNAS Intel)

# Stage 1: Base image with system dependencies
FROM python:3.11-slim-bullseye AS base

# Install system dependencies for Playwright, Selenium, and VNC
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    curl \
    x11vnc \
    xvfb \
    fluxbox \
    unzip \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Install Python dependencies
FROM base AS deps

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium && \
    playwright install-deps chromium

# Download and install noVNC for web-based VNC access
RUN wget https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz && \
    tar xzf v1.4.0.tar.gz && \
    mkdir -p /app/static && \
    mv noVNC-1.4.0 /app/static/novnc && \
    rm v1.4.0.tar.gz

# Stage 3: Final runtime image
FROM base AS runtime

WORKDIR /app

# Copy Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy noVNC files from deps stage
COPY --from=deps /app/static/novnc /app/static/novnc

# Copy application code
COPY app/ ./app/

# Copy VNC startup script and entrypoint
COPY start-vnc.sh /usr/local/bin/
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/start-vnc.sh /usr/local/bin/docker-entrypoint.sh

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Create data directory with proper permissions
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app/data

# Fix permissions for Chromium/Chromedriver (needed for Selenium)
RUN chmod 755 /usr/bin/chromium /usr/bin/chromedriver

# Copy Playwright browsers and set permissions for appuser
COPY --from=deps /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright
RUN chown -R appuser:appuser /home/appuser/.cache

# Switch to non-root user
USER appuser

# Expose ports
EXPOSE 8080
EXPOSE 5900
EXPOSE 6080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application with VNC support
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
