FROM python:3.12-alpine
WORKDIR /app

# Install necessary packages including ca-certificates and openssl
RUN apk update && \
    apk add --no-cache \
        ffmpeg \
        jq \
        python3-dev \
        ca-certificates \
        openssl \
        openssl-dev \
        gcc \
        musl-dev \
        libffi-dev && \
    update-ca-certificates

# Copy and install requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Verify yt-dlp installation
RUN python3 -m pip check yt-dlp

# Set SSL environment variables
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

CMD ["python3", "bot.py"]
