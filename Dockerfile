FROM bobby-base:v0.1.0

# Thiết lập lại biến môi trường để đồng bộ
ENV PYTHONPATH=/app
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# 1. Chỉ copy pyproject.toml để tận dụng cache layer
COPY pyproject.toml ./


RUN rm -f poetry.lock && \
    poetry lock && \
    poetry install --no-root --no-interaction --no-ansi

# 3. Copy toàn bộ source code vào sau cùng
COPY . /app