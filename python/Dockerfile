FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir ".[mysql]"

EXPOSE 3001

CMD ["knowledgeops-python-api"]
