FROM python:3.14-slim
WORKDIR /app
COPY app.py seed_demo.py ./
COPY static ./static
ENV HOST=0.0.0.0 PORT=8000 DB_PATH=/data/mundial.db PYTHONUNBUFFERED=1
RUN groupadd -g 10001 lab && useradd -u 10001 -g lab lab && mkdir /data && chown lab:lab /data
USER lab
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health',timeout=2)"
CMD ["python", "app.py"]
