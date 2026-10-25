# syntax=docker/dockerfile:1
# The Nametags API in one image: Python 3.12, dlib built from source, the face and voice packages,
# and the speech models baked in. Postgres runs beside it (docker-compose.yml).

FROM python:3.12-slim-bookworm AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake pkg-config libopenblas-dev liblapack-dev curl ca-certificates bzip2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.12

# Dependencies first, so they are rebuilt only when the lock or a subproject changes.
COPY pyproject.toml uv.lock ./
COPY facial-recognition-foundation-46999b/pyproject.toml facial-recognition-foundation-46999b/
COPY facial-recognition-foundation-46999b/facerec facial-recognition-foundation-46999b/facerec
COPY hackpsu_voice_rec/pyproject.toml hackpsu_voice_rec/
COPY hackpsu_voice_rec/voice_rec hackpsu_voice_rec/voice_rec
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

# The speaker, VAD and speech-to-text models (no TTS: the frontend speaks).
COPY hackpsu_voice_rec/scripts/download_models.sh hackpsu_voice_rec/scripts/
RUN bash hackpsu_voice_rec/scripts/download_models.sh --no-tts

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 libgomp1 libgl1 libglib2.0-0 libsndfile1 libportaudio2 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/hackpsu_voice_rec/models /app/hackpsu_voice_rec/models
COPY . .
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NAMETAGS_DATA=/data \
    VOICEREC_MODEL=/app/hackpsu_voice_rec/models/nemo_en_titanet_small.onnx \
    VOICEREC_VAD_MODEL=/app/hackpsu_voice_rec/models/silero_vad.onnx \
    VOICEREC_ASR_MODEL=/app/hackpsu_voice_rec/models/sherpa-onnx-moonshine-base-en-int8
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
