FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Окремо ставимо залежності, щоб ефективніше використовувати кеш шарів
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Стан зберігається у /app/data (підписники, налаштування, статистика)
VOLUME ["/app/data"]

CMD ["python", "-u", "bot.py"]
