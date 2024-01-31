# syntax=docker/dockerfile:1
# Keep this syntax directive! It's used to enable Docker BuildKit
# Modified from https://nanmu.me/en/posts/2023/quick-dockerfile-for-python-poetry-projects/
# See poetry build cache discussion here: https://github.com/orgs/python-poetry/discussions/1879
# and https://nanmu.me/en/posts/2023/quick-dockerfile-for-python-poetry-projects/


################################
# PYTHON-BASE
# Sets up all our shared environment variables
################################
FROM python:3.11-slim as python-base

# Python
ENV PYTHONUNBUFFERED=1 \
    # pip
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # Poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=1.7.1 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    # never create virtual environment automaticly, only use env prepared by us
    POETRY_VIRTUALENVS_CREATE=false \
    \
    # this is where our requirements + virtual environment will live
    VIRTUAL_ENV="/venv" 

# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VIRTUAL_ENV/bin:$PATH"

# prepare virtual env
RUN python -m venv $VIRTUAL_ENV

# working directory and Python path
WORKDIR /app
ENV PYTHONPATH="/app:$PYTHONPATH"


################################
# BUILDER-BASE
# Used to build deps + create our virtual environment
################################
FROM python-base as builder-base
RUN apt-get update && \
    apt-get install -y \
    apt-transport-https \
    gnupg \
    ca-certificates \
    build-essential \
    git \
    nano \
    curl

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
# The --mount will mount the buildx cache directory to where
# Poetry and Pip store their cache so that they can re-use it
RUN --mount=type=cache,target=/root/.cache \
    curl -sSL https://install.python-poetry.org | python -

# used to init dependencies
WORKDIR /app
COPY poetry.lock* pyproject.toml ./
COPY {{cookiecutter.project_slug}}/ {{cookiecutter.project_slug}}/

# install runtime deps to VIRTUAL_ENV
# exclude test and lint dependencies (defined in pyproject.toml)
RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-root --only main,dagster-min


################################
# DEVELOPMENT
# Image used during development / testing
################################
FROM builder-base as local

WORKDIR /app

# quicker install as runtime deps are already installed
# Also avoid installing unnecessary dagster dependencies with --without dagster-full (defined in pyproject.toml)
RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-root --with lint

# Run dagster gRPC server on port 4000
EXPOSE 4000
# CMD allows this to be overridden from run launchers or executors that want
# to run other commands against your repository
CMD ["dagster", "code-server", "start", "-h", "0.0.0.0", "-p", "4000", "-m", "{{cookiecutter.project_slug}}"]

################################
# PRODUCTION
# Final image used for runtime
################################
FROM python-base as production

# Create a container user so that we don't run as root in production
ARG CONTAINER_USER=dagster
RUN addgroup --system $CONTAINER_USER \
    && adduser --system --ingroup $CONTAINER_USER $CONTAINER_USER

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates && \
    apt-get clean

# copy in our built poetry + venv
# Uncomment to keep poetry in production build
# COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $VIRTUAL_ENV $VIRTUAL_ENV

WORKDIR /app
ARG HOME_DIR=/app

# Copy the repository code
COPY --chown=$CONTAINER_USER:$CONTAINER_USER ./{{cookiecutter.project_slug}} ./{{cookiecutter.project_slug}}

# Make dagster user owner of the WORKDIR directory as well.
RUN chown $CONTAINER_USER:$CONTAINER_USER ${HOME_DIR}
# Switch to dagster user
USER $CONTAINER_USER

EXPOSE 4000
CMD ["dagster", "api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-m", "{{cookiecutter.project_slug}}"]


