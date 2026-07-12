# Build the FastAPI application layer on top of the vendor ML model base image.
# BASE_IMAGE is injected by CI (GitHub Actions) from ECR, e.g.:
#   <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/mlscan-models:base-pe-<version>
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

WORKDIR /srv
COPY pe/requirements.txt /srv/requirements.txt
RUN python3 -m ensurepip --upgrade && \
    python3 -m pip install --no-cache-dir -r /srv/requirements.txt

COPY common /srv/common
COPY pe/main.py pe/model_adapter.py /srv/

ENV PYTHONUNBUFFERED=1 \
    AWS_REGION=us-east-1 \
    MODEL_MODE=stub \
    SAI_API_CONFIG_PATH=/usr/src/app/config.ini \
    SYSTEM=internal \
    PYTHONPATH=/srv

EXPOSE 8080

# Start from /usr/src/app so the vendor SDK resolves relative model weight paths correctly.
ENTRYPOINT []
CMD ["bash", "-c", "cd /usr/src/app && exec uvicorn main:app --host 0.0.0.0 --port 8080"]
