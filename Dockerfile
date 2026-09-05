# spark-fleet-updates — the controller. Stdlib Python plus an ssh client;
# nothing else. State lives in /data; the ssh key is mounted read-only.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client openssl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 fleet
WORKDIR /app
COPY spark_fleet/ /app/spark_fleet/
ENV SPARK_FLEET_DATA=/data \
    SPARK_FLEET_PORT=8080 \
    SPARK_FLEET_INTERVAL_MIN=60 \
    SPARK_FLEET_SSH_KEY=/ssh/id_ed25519 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown fleet:fleet /data
USER fleet
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=5s CMD python3 -c "import urllib.request,ssl;c=ssl._create_unverified_context();[urllib.request.urlopen(u,timeout=4,context=c if u.startswith('https') else None) for u in ['https://127.0.0.1:8080/api/fleet']]" || python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/api/fleet',timeout=4)" || exit 1
CMD ["python3", "-m", "spark_fleet"]
