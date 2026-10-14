"""Derive stable document IDs for the v1.1 benchmark corpus.

Uses the identical SHA-256(raw_file_bytes) mechanism as KIP's DocumentIngestionService.
Run from the repository root: python benchmarks/derive_corpus_ids.py
"""

import hashlib
import pathlib

CORPUS_DIR = pathlib.Path("benchmarks/corpus")

for txt_file in sorted(CORPUS_DIR.glob("*.txt")):
    raw_bytes = txt_file.read_bytes()
    doc_id = hashlib.sha256(raw_bytes).hexdigest()
    size = len(raw_bytes)
    # Verify the file has LF line endings (no CR bytes) for platform stability
    has_cr = b"\r" in raw_bytes
    print(f"{txt_file.name}")
    print(f"  document_id : {doc_id}")
    print(f"  size_bytes  : {size}")
    print(f"  has_CRLF    : {has_cr}")
    print()
