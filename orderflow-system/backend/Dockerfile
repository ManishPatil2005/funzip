FROM python:3.13-slim
WORKDIR /app
RUN useradd -r -u 10001 ofx
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ofx ./ofx
USER ofx
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "ofx.main:app", "--host", "0.0.0.0", "--port", "8000"]
