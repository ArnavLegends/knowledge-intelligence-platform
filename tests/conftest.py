"""Pytest configuration and global fixtures."""

import os

# Enforce ephemeral (in-memory) ChromaDB for all tests to prevent
# .chroma_data directory generation in the project root.
os.environ["VECTOR_STORE_PERSIST_DIRECTORY"] = ""
