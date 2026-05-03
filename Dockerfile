FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -e .

COPY . .

RUN playwright install chromium --with-deps

EXPOSE 8080

CMD ["uvicorn", "job_agent.interfaces.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
