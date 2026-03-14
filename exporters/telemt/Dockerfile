FROM python:3.11-alpine

RUN pip install --no-cache-dir urllib3

WORKDIR /app
COPY main.py .

EXPOSE 9104

CMD ["python", "-u", "main.py"]
