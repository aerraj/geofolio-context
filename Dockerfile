FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir . && useradd --create-home geofolio && mkdir /data && chown geofolio:geofolio /data
USER geofolio
EXPOSE 8000
CMD ["geofolio", "serve", "--mode", "live", "--host", "0.0.0.0", "--data-dir", "/data"]
