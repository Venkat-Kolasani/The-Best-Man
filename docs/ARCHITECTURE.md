# Architecture

## Overview

## Ingestion Flow

The repository ingestion API starts work asynchronously. `POST /repos/{owner}/{repo}/ingest`
returns a `job_id` immediately, and the caller polls `GET /repos/{owner}/{repo}/ingest/{job_id}`
for `queued`, `running`, `done`, or `failed` status.

For hackathon demo simplicity, job status is stored in a module-level in-memory dictionary inside
the FastAPI process. This keeps the implementation small and easy to reason about during local
development and live demos.

This design has important limitations:
- Job state is lost if the server restarts.
- Job state is not shared across multiple API workers or replicas.
- It is not suitable for durable background processing in production.
- Quota-driven upstream retries, such as Gemini embedding `429 RESOURCE_EXHAUSTED` responses,
  can make Cognee run for a long time. To avoid demo jobs staying `running` indefinitely, the
  background wrapper applies a timeout and marks the job `failed` if ingestion does not complete
  within the configured demo window.

Production-ready alternatives include Redis-backed job state, a database job table, or a proper
task queue such as Celery, RQ, Arq, or a managed workflow system.

## Recall Flow

## Improve Flow

## Forget Flow

## Data Model
