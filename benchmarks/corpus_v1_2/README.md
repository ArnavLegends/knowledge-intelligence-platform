# KIP Evaluation Corpus — v1.2 Input Formatting Experiment

## Purpose

This directory contains the expanded 18-document reference corpus used for the KIP v1.2 retrieval evaluation and Gemini Embedding 2 input formatting experiment. The corpus expands beyond the 3 documents in v1.1 to eliminate degenerate Hit Rate@5 values and evaluate retrieval accuracy across core KIP architectures and adversarial distractors.

## Corpus Documents

| File | Size (bytes) | Document ID | Topic |
|------|-------------|-------------|-------|
| `distractor_alternative_chunkers.txt` | 844 | `6ff7d746e04a224f077f3f5d56a24d27897cb1937b239cae74cd88beb9862309` | Distractor: Alternative chunking schemes |
| `distractor_external_judge_evaluators.txt` | 805 | `8774fafef3374318b636ba522a75f6c1958114f67340e0cd4f3faf9bafee6007` | Distractor: LLM-as-judge evaluation frameworks |
| `distractor_hybrid_search_proposals.txt` | 830 | `bcae8ec7dcddee5cfda148a3f27a5b270940ff4a0792d2bd70d53092debbbaad` | Distractor: Hybrid BM25/dense proposals |
| `distractor_legacy_chroma_settings.txt` | 739 | `8b0226bcfa741d718ffcb4aed64b322e7378b3b79ec4c7a9562f5459183b6daf` | Distractor: Deprecated Chroma vector store |
| `kip_api_specifications.txt` | 729 | `94537d50db3b489518a96a150e5ceca48062c1cacee542948be31c0b34e23f16` | API endpoints and request schemas |
| `kip_chunking_and_embeddings.txt` | 844 | `42fdd2502a96a31974aad6a476bdba4c28fe896cf126d25ca984f6cc7f551bd9` | Chunking parameters and chunk ID generation |
| `kip_configuration_settings.txt` | 663 | `f31afadf457b1b24713343f87f80b916c3f1b02511f854f8add8fddbbb96eb7d` | Environment variables and pydantic settings |
| `kip_document_parsers.txt` | 780 | `717a9f50e6e87d50545083a0da382aaea9043e2fa7781941f449a01a97a17939` | Ingestion parsers and upload limits |
| `kip_evaluation_framework.txt` | 748 | `61be0048f3bcc9b0032a5a14e636b8cd3fe3a079ef222039e49c1e95a2675248` | Evaluation runner and metrics definitions |
| `kip_feedback_webhook.txt` | 756 | `90f1120fd93dba87c023f02cfa0b13726f46e95f8b23693f55e9c831a48cd9d7` | Google Sheets feedback webhook integration |
| `kip_grounded_rag_prompting.txt` | 781 | `9c2b2af9079f91e5bee81cf4a43dd0e6f405721e76a83dc519fb7042ab7ddb07` | Context assembly and grounded generation |
| `kip_idempotency_service.txt` | 847 | `44635d7bb2910fd6538a43fbed5cc5b14713bad093370da182c29541bb326028` | Content-addressed idempotency guarantees |
| `kip_llm_gateway.txt` | 764 | `792a97f6d3e29ba1334383183367a7954bfbc4cf5635d4a5381122be1049ee15` | Gemini LLM provider adapter |
| `kip_multitenancy_architecture.txt` | 896 | `f88a2b872f8703152c22f9e6d0ec0fc5c71e998e610ce2a2bcd170af13121817` | Multitenancy and workspace payload filtering |
| `kip_overview.txt` | 893 | `07123957b17b180eef3505c6b2dc1f76a161cedcc618081eb882de99dbf2a324` | High-level architecture and platform overview |
| `kip_retrieval_and_rag.txt` | 799 | `c018e2ecd67d7fae0592d751086f9ee5c5496ded23692bbbf1f74d112b14aa14` | Semantic vector search and RAG orchestration |
| `kip_security_threat_model.txt` | 769 | `c23047dbd82181c11741ec45dfbb3e2304da4927e6f21afe361e3433df1a1fc7` | Security boundaries and tenant isolation |
| `kip_vector_store_adapters.txt` | 801 | `8a37b15d83ff34d26a438dd4a57fcb6eb422fe6b5ec5e3ed57b2cc22175c4b83` | Vector store provider abstraction layer |

## Design Constraints

- **LF line endings only:** All corpus files use Unix LF (`\n`) exclusively.
- **Content-frozen:** Document IDs are derived as `SHA-256(raw_file_bytes)`.
- **Top-5 Coverage:** Each document chunks into 1 chunk (700-900 chars) under `FixedSizeChunker(1000, 200)`, resulting in 18 candidate chunks. Top-5 retrieval retrieves 5/18 (~28%) of the corpus, providing meaningful discriminative signal for Hit Rate@1, Hit Rate@3, Hit Rate@5, and MRR.
