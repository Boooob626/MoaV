FROM python:3.11-alpine

# Install docker CLI (needed to tail container logs)
RUN apk add --no-cache docker-cli

RUN pip install --no-cache-dir maxminddb

WORKDIR /app
COPY lib/geoip.py .
COPY xray/main.py .

EXPOSE 9103

CMD ["python", "-u", "main.py"]
