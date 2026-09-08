# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim-bookworm

ARG POETRY_VERSION=2.2.1
ARG POETRY_PLUGIN_EXPORT_VERSION=1.9.0

COPY --from=node-runtime /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        git \
        libffi-dev \
        libssl-dev \
        make \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    "poetry==${POETRY_VERSION}" \
    "poetry-plugin-export==${POETRY_PLUGIN_EXPORT_VERSION}"

ENV CI=true \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

WORKDIR /workspace
