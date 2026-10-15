# Docker

This directory will contain containerization and deployment configuration for the Knowledge Intelligence Platform.

## Planned Contents

- Dockerfiles for backend and frontend services
- Docker Compose definitions for local development
- Production deployment configurations
- Container-related helper scripts

## Development & Deployment Context

KIP v1.3 is deployed zero-cost across managed cloud services without requiring self-hosted containers:
- **Frontend:** Streamlit Community Cloud (native Python runtime)
- **Backend:** Render Web Service (native Python runtime)
- **Vector Database:** Qdrant Cloud Free Tier cluster

For local development and offline evaluation, Docker can be used to run a local Qdrant instance:

```bash
docker run -d -p 6333:6333 qdrant/qdrant:latest
```

Formal containerization (Dockerfiles and docker-compose configurations for full self-hosted deployments) is planned for the v1.8 technical packaging milestone and conditional v3.2 cloud operations.

## Related Documentation

- [Deployment Guide](../docs/deployment.md) — Current production free-tier topology
- [Architecture](../docs/Architecture.md) — System architecture
- [Product Roadmap](../docs/Product-Roadmap.md) — Planned packaging milestones
