FROM python:3.11-slim

ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8000

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . .

RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
