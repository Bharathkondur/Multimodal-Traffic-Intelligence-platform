# Changelog

All notable changes to the Multimodal Traffic Intelligence Platform are documented here.

## [Unreleased]

### Planned
- Support for multi-camera stream federation
- Export detections to CSV/JSON via dashboard UI
- Alert webhook integrations (Slack, PagerDuty)

## [1.3.0] - 2026-04-04

### Added
- `backend/utils/health_check.py`: async health check utilities for PostgreSQL, Redis, and ML model files
- Checks run concurrently via `asyncio.gather` for fast liveness/readiness probes
- Returns per-service latency and an overall `healthy` flag suitable for container orchestration

## [1.2.0] - 2026-03-28

### Added
- Interactive SVG dashboard preview in README
- Portfolio cleanup: removed dev artifacts, tightened `.gitignore`

## [1.1.0] - 2025-12-10

### Added
- LangGraph reasoning agent with RAG over detection events
- Natural language Q&A endpoint (`/api/query`)
- Automated shift report generation
- Grafana dashboards for real-time metrics

### Improved
- WebSocket stream stability under high detection load
- Plate recognition accuracy with preprocessing pipeline

## [1.0.0] - 2025-10-15

### Added
- Initial release of Multimodal Traffic Intelligence Platform
- YOLOv8-based vehicle, pedestrian, and cyclist detection
- License plate recognition and extraction
- Incident detection: stopped vehicles, congestion, crowd formations
- FastAPI backend with async PostgreSQL via SQLAlchemy
- React + Tailwind frontend with live WebSocket dashboard
- Docker Compose setup for full-stack local deployment
- Prometheus metrics and structured logging
