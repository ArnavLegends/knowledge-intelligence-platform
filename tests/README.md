# Tests

This directory contains automated tests for the Knowledge Intelligence Platform.

## Intended Contents

- Unit tests for backend services and utilities
- Integration tests for API endpoints and pipelines
- Regression tests for critical workflows
- Scaffold and infrastructure validation tests

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov --cov-report=term-missing
```

## Development Milestone

The testing framework is established during **v0.1** with scaffold validation tests. Comprehensive backend and integration tests will be added starting in **v0.2**.

## Related Documentation

- [Development Workflow](../docs/Development-Workflow.md)
- [Software Requirements Specification](../docs/SRS.md)
