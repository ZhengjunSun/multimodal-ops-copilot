FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV OPS_DATABASE=/data/ops-copilot.db OPS_ARTIFACT_ROOT=/data/artifacts
VOLUME ["/data"]
EXPOSE 8010
CMD ["uvicorn","ops_copilot.api:app","--host","0.0.0.0","--port","8010"]
