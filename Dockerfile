FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT defaults to 8080 -- GreenNode AgentRuntime (the deploy target for
# this image) requires the app to listen on 8080. Override with -e PORT=...
# for other environments.
ENV PORT=8080
EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8080') + '/health')" || exit 1

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
