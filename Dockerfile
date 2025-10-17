FROM python:3.12-alpine
WORKDIR /app
RUN apk update && \
    apk add --no-cache ffmpeg jq python3-dev ca-certificates
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python3 -m pip check yt-dlp
CMD ["python3", "bot.py"]
