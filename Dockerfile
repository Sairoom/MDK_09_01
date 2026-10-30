FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0
COPY app app
COPY wsgi.py .
RUN mkdir -p /app/instance && useradd --create-home portal && chown -R portal:portal /app
USER portal
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "wsgi:app"]
