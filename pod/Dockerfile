FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim



# Install ffmpeg (includes ffprobe)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /pod

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY main.py ./
COPY ./apps ./apps
COPY ./settings ./settings
COPY ./services ./services
COPY ./utility ./utility
COPY ./static ./static

RUN uv sync --locked
RUN uv run -- spacy download en_core_web_sm

# CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# CMD ["uv", "run", "taskiq", "worker", "settings.my_taskiq:broker"]
# CMD ["uv", "run", "taskiq", "scheduler", "settings.my_taskiq:scheduler"]