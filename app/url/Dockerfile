# Build the URL scan API service on top of the pre-built ML model base image.
# BASE_IMAGE is injected by CI (points to the ECR base tag for the current model version).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

WORKDIR /srv
COPY url/requirements.txt /srv/requirements.txt
RUN python3 -m ensurepip --upgrade && \
    python3 -m pip install --no-cache-dir -r /srv/requirements.txt

COPY common /srv/common
COPY url/main.py url/model_adapter.py /srv/

ENV PYTHONUNBUFFERED=1 \
    AWS_REGION=eu-west-2 \
    MODEL_MODE=stub \
    SAI_API_CONFIG_PATH=/usr/src/app/config.ini \
    SYSTEM=internal \
    PYTHONPATH=/srv
EXPOSE 8080

# Run from /usr/src/app so the ML SDK resolves relative weight paths in config.ini correctly.
ENTRYPOINT []
CMD ["bash", "-c", "cd /usr/src/app && exec uvicorn main:app --host 0.0.0.0 --port 8080"]
