# Knowledge Intelligence Platform

> A modular AI Knowledge Intelligence Platform for Retrieval-Augmented Generation (RAG).

[![Build Status](https://github.com/knowledge-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/knowledge-intelligence-platform/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

The Knowledge Intelligence Platform (KIP) is a robust, production-oriented knowledge assistant capable of retrieving, understanding, and synthesizing information from documents. 

Designed with modern AI engineering practices, this platform currently implements a complete FastAPI-based Retrieval-Augmented Generation (RAG) backend engine, built to support future exploration into agentic workflows, multimodal intelligence, and knowledge graphs.

## Current Project Status

**Status: Core Foundation & Backend APIs Implemented**

The repository currently provides a fully functional backend API for document ingestion, chunking, semantic retrieval, and OpenAI-backed generation. A comprehensive test suite ensures architectural stability. Research and evaluation frameworks are planned but not yet active.

### What is Implemented Today
- **Document Ingestion**: Parsing for TXT files.
- **Chunking Pipeline**: Configurable chunking with overlap.
- **Embedding Integration**: OpenAI embeddings adapter.
- **Vector Storage**: Ephemeral and persistent ChromaDB adapter.
- **Semantic Retrieval**: Top-k similarity search with thresholds.
- **RAG Generation**: Orchestrated response generation via OpenAI models.
- **REST APIs**: Versioned endpoints for documents, retrieval, and RAG.

## Technology Stack

### Current Technologies
- **Core**: Python 3.11+
- **API Framework**: FastAPI, Pydantic, pydantic-settings
- **AI/LLM SDK**: OpenAI Python SDK
- **Vector Database**: ChromaDB
- **Quality & Testing**: Pytest, Ruff, GitHub Actions CI

### Planned Technologies
The following are planned for future major releases:
- **Frontend**: Streamlit, React
- **Agent/AI Frameworks**: LangChain, LangGraph
- **Additional LLMs**: Anthropic, Google Gemini, Local LLMs
- **Databases/Graphs**: PostgreSQL, Neo4j, Pinecone, Weaviate
- **Evaluation**: RAGAS, DeepEval

## Architecture Path (Current)

```
Document -> Chunk -> Embedding -> Vector Store -> Retrieval -> Context Assembly -> LLM -> RAG Response
```

## Quick Start & Local Development

### Prerequisites
- Python 3.11+
- `pip` or `hatch` for environment management
- OpenAI API Key

### Installation

```bash
git clone https://github.com/your-org/knowledge-intelligence-platform.git
cd knowledge-intelligence-platform

# Install dependencies (development mode recommended)
pip install -e ".[dev]"
```

### Configuration
Copy the `.env.example` file to `.env` and configure your API keys:
```bash
cp .env.example .env
# Edit .env to add OPENAI_API_KEY
```

### Running the Server
```bash
uvicorn app.main:app --reload
```
The API documentation will be available at `http://localhost:8000/docs`.

## Testing and Code Quality

The project maintains high code quality standards. GitHub Actions CI automatically validates all pull requests.

- **Tests**: Run `python -m pytest -v` (Our test suite uses in-memory mocked ChromaDB for isolation).
- **Linting**: Run `python -m ruff check .`
- **Formatting**: Run `python -m ruff format --check .`

## Documentation

- [API Reference](docs/API-Reference.md)
- [Product Roadmap](docs/Product-Roadmap.md)
- [Architecture](docs/Architecture.md)
- [Research Roadmap](docs/Research-Roadmap.md)
- [Benchmarking Strategy](docs/Benchmarking.md)
- [Changelog](docs/Changelog.md)

## Engineering Principles

1. **Production First**: Design with maintainability, reliability, and modularity in mind.
2. **Modular Architecture**: Subsystems remain loosely coupled (e.g. interchangeable vector DBs).
3. **Version-Based Evolution**: Stable, incremental releases.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.