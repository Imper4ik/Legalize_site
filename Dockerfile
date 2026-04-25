FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext \
    fonts-dejavu-core \
    fonts-noto-core \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-pol \
    poppler-utils \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY requirements-dev.txt /app/requirements-dev.txt

RUN pip install --upgrade pip && pip install -r /app/requirements-dev.txt

COPY . /app

RUN chmod +x /app/start.sh \
    && python manage.py compilemessages --ignore "venv" --ignore ".venv" \
    && DJANGO_SETTINGS_MODULE=legalize_site.settings.test pytest --maxfail=1 -q \
    && python manage.py collectstatic --no-input

CMD ["bash", "/app/start.sh"]
