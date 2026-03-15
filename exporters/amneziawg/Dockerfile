FROM python:3.11-alpine

# Install docker CLI (to run docker exec)
RUN apk add --no-cache docker-cli

RUN pip install --no-cache-dir maxminddb

WORKDIR /app
COPY lib/geoip.py .
COPY amneziawg/main.py .

EXPOSE 9587

CMD ["python", "-u", "main.py"]
