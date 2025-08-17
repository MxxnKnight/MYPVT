FROM python:3.14-rc-alpine3.20
WORKDIR /app
RUN RUN apk add --no-cache ffmpeg jq python3-dev
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python3 -m pip check yt-dlp
CMD ["python3", "bot.py"]
