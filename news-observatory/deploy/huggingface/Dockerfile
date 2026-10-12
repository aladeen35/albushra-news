# Hugging Face Spaces: same image as backend/Dockerfile, laid out for a Space
# whose root holds backend/ and frontend/. Spaces expect port 7860.
FROM python:3.12-slim
WORKDIR /srv/backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRONTEND_DIR=/srv/frontend \
    PORT=7860 DATABASE_URL=sqlite:////tmp/albushra.db SCHEDULER_ENABLED=true \
    HDX_APP_NAME=albushra-news HDX_APP_EMAIL=albushra-news@users.noreply.github.com
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY frontend /srv/frontend
RUN useradd --system --uid 1000 app
USER app
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
