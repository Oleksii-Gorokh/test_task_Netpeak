FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY input_requests.csv ./input_requests.csv

ENTRYPOINT ["python", "-m", "request_triage"]

