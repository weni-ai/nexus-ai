FROM python:3.10-slim

ENV WORKDIR /app
WORKDIR $WORKDIR

RUN pip install poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --only main

COPY . .

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["bash", "-e", "/entrypoint.sh"]