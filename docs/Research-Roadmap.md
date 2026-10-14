# Research Roadmap

**Document Version:** 2.1  
**Project Version:** v1.2 (Research Phase — Experiments Complete)  
**Status:** Active — v1.2 Research Concluded  

---

## Purpose

This document defines the long-term research strategy for the Knowledge Intelligence Platform.

While the Product Roadmap describes what will be built, the Research Roadmap defines what questions the project aims to investigate, evaluate, and better understand through systematic experimentation.

The roadmap provides a structured framework for conducting reproducible AI systems research alongside product development, ensuring that engineering decisions are supported by empirical evidence rather than assumptions.

The objective is not only to build an intelligent platform but also to generate practical insights into modern AI system design through disciplined experimentation and evaluation.

---

## Research Philosophy

Research is treated as an integral part of the engineering lifecycle rather than as a separate activity.

Every major architectural decision should be motivated by clearly defined research questions, evaluated through reproducible experiments, and documented with transparent methodology and measurable results.

The platform emphasizes applied AI systems research, where experimental findings directly influence engineering improvements, architectural evolution, and future development priorities.

Research activities should prioritize reproducibility, objectivity, and practical impact over novelty alone.

> **Research Infrastructure Status (v1.2):**  
> The core evaluation harness (`evaluation/models.py`, `evaluation/runner.py`) was implemented and verified in v1.0.0. In v1.2, the evaluation infrastructure was expanded to a 50-document corpus (`benchmarks/corpus_v1_2_expanded/`) and 80-case benchmark (`benchmarks/kip_v1_2_expanded_benchmark.json`) covering six query categories (`exact_terminology`, `paraphrase`, `hard_negative`, `multi_concept`, `boundary_handling`, `cross_document`). Four controlled retrieval experiments were executed against this frozen benchmark under the 14-step research lifecycle. **All four candidates were rejected** — none reached the preregistered primary MRR target of ≥ 0.8200. Dense whole-document retrieval (MRR 0.7623) remains the production default pending a synthesis approach.

---

## Research Objectives

The long-term research objectives of the Knowledge Intelligence Platform include:

### 1. Improve Retrieval Quality

Investigate retrieval strategies that maximize context relevance while minimizing irrelevant information presented to language models.

### 2. Improve Reasoning Quality

Study methods that improve multi-step reasoning, information synthesis, and explainability.

### 3. Evaluate AI Architectures

Compare different AI system architectures including Retrieval-Augmented Generation (RAG), memory systems, agentic workflows, and hybrid knowledge systems.

### 4. Develop Reproducible Benchmarks

Create standardized evaluation procedures capable of comparing models, retrieval methods, and system architectures across multiple project versions.

### 5. Understand Trade-offs

Investigate trade-offs involving accuracy, latency, scalability, computational cost, and engineering complexity.

### 6. Support Evidence-Based Engineering

Ensure that future engineering decisions are guided by measurable experimental evidence rather than intuition.

---

## Research Domains

The Knowledge Intelligence Platform investigates multiple areas of modern AI systems engineering. These domains evolve alongside product development and collectively define the long-term research direction of the project.

### Retrieval Systems

- Dense Retrieval (Implemented: Gemini `gemini-embedding-2`, OpenAI `text-embedding-3-small`)
- Sparse Retrieval (Evaluated: BM25 + RRF — Rejected in v1.2, MRR 0.6554 vs baseline 0.7623)
- Hybrid Retrieval (Evaluated: BM25 + Dense RRF — Rejected in v1.2; see `docs/evaluation/v1.2_hybrid_retrieval_experiment.md`)
- Query Expansion (Planned: HyDE / multi-query)
- Metadata Filtering (Implemented: `workspace_id` payload filter)
- Reranking (Evaluated: Cross-Encoder `ms-marco-MiniLM-L-6-v2` — Rejected in v1.2, latency +1,048 ms; see `docs/evaluation/v1.2_cross_encoder_experiment.md`)
- Context Selection (Implemented: Top-K truncation)

### Language Models

- Prompt Engineering (Implemented: v1 deterministic prompt template)
- Context Window Optimization
- Model Comparison (Implemented: Gemini 2.5 Flash vs OpenAI GPT-4o-mini)
- Response Grounding (Implemented: Provenance attribution card)
- Hallucination Reduction
- Response Quality Analysis

### AI Memory (Deferred)

- Short-Term Memory
- Long-Term Memory
- Memory Compression
- Context Prioritization
- Memory Retrieval Strategies

### Agentic AI (Deferred)

- Planning Algorithms
- Multi-Step Reasoning
- Tool Calling
- Workflow Optimization
- Multi-Agent Collaboration

### Knowledge Representation

- Vector Databases (Implemented: ChromaDB & Qdrant Cloud)
- Knowledge Graphs (Deferred)
- Entity Linking (Deferred)
- Relationship Extraction (Deferred)
- Hybrid Knowledge Systems (Deferred)

### Multimodal Intelligence (Deferred)

- Image Understanding
- OCR
- Audio Processing
- Cross-Modal Retrieval
- Unified Knowledge Representation

### AI Evaluation

- Retrieval Benchmarks (Implemented: `benchmarks/kip_v1_baseline.json`)
- Response Evaluation (Implemented: `evaluation/runner.py`)
- Latency Analysis
- Explainability (Implemented: Provenance source citations)
- Reliability & Error Classification (Implemented: Top-K empty vs zero-doc distinction)
- Robustness

---

## Evaluation Methodology

Every significant engineering improvement should be evaluated using a standardized methodology to ensure that experimental results remain reproducible and comparable across project versions.

### Evaluation Principles

- Reproducibility
- Fair comparison
- Objective measurement
- Transparent reporting
- Statistical consistency
- Repeatable experiments

### Evaluation Categories

#### Retrieval Performance

- Precision
- Recall
- Mean Reciprocal Rank (MRR) (Implemented in `evaluation/runner.py`)
- Normalized Discounted Cumulative Gain (NDCG)
- Hit Rate (Implemented in `evaluation/runner.py`)

#### Response Quality

- Faithfulness (Planned: v1.2, requires LLM judge)
- Answer Relevance (Planned: v1.2, requires LLM judge)
- Context Relevance
- Completeness
- Hallucination Rate (Planned: v1.2, requires LLM judge)
- Keyword Coverage (Implemented in `evaluation/runner.py`)
- Exact Match (Planned: optional schema in `evaluation/models.py`)

#### System Performance

- Latency (Retrieval, Generation, Total) (Implemented in `evaluation/runner.py`)
- Latency Profiling (p50, p95, p99) (Planned: v1.3)
- Throughput (requests/sec)
- Memory Usage
- Storage Requirements

#### User Experience

- Response Consistency
- Explainability (Provenance cards)
- User Feedback Sentiment (Implemented via feedback webhook)
- Reliability

---

## 14-Step Systematic Research Lifecycle

To ensure scientific rigor and reproducible engineering, all future research experiments (starting in v1.2) must follow the formalized 14-step research lifecycle:

1. **Literature Review:** Survey existing academic literature, benchmarks, and industrial state of the art.
2. **Gap Analysis:** Identify specific limitations in current KIP architecture or retrieval baselines.
3. **Research Question:** Formulate falsifiable, hypothesis-driven research questions.
4. **Benchmark / Test Set:** Define standardized datasets with ground truth queries, relevance judgments, and expected answers.
5. **Dense Retrieval Baseline:** Execute the baseline dense retrieval pipeline (`evaluation/runner.py`) to record initial metrics.
6. **Chunking / Segmentation Experiment:** Test alternative document chunking algorithms (semantic, sentence-boundary, recursive).
7. **Hybrid Retrieval:** Implement and test sparse + dense fusion (e.g., BM25 + Qdrant vectors with RRF).
8. **Reranking:** Evaluate cross-encoder rerankers on top-N candidates to optimize NDCG and Precision.
9. **Context Optimization:** Test context compression, deduplication, and dynamic prompt budget allocation.
10. **Metrics Collection:** Gather automated Hit Rate, MRR, NDCG, faithfulness, and execution latency.
11. **Results Analysis:** Statistically compare experimental results against dense baselines.
12. **Decision Gate:** Formally decide whether performance gains justify computational cost and code complexity.
13. **Integration:** Merge validated improvements into core production RAG pipeline.
14. **Deprecation & Documentation:** Update architecture documents, deprecate inferior methods, and archive baseline run logs.

---

## Research Records

### CHUNK-BASELINE-001

**Status:** Baseline Established (v0.3.0 / v1.0.0)  
**Strategy:** Fixed-size character chunking with sliding window overlap  
**Initial Configuration:** `chunk_size = 1000`, `chunk_overlap = 200`  
**Variables:** chunk size, overlap  

**Purpose:** Establish a deterministic baseline for future chunking experiments.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### EMBED-BASELINE-001

**Status:** Baseline Established (v0.3.0 / v1.0.0)  
**Strategy:** OpenAI dense embedding  
**Configuration:** `provider = openai`, `model = text-embedding-3-small`, `dimensions = 1536`  
**Variables:** embedding model, dimensionality, batch/input size  

**Purpose:** Establish a reproducible embedding baseline for retrieval experiments.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### EMBED-BASELINE-002

**Status:** Baseline Established (v1.1.0)  
**Strategy:** Google Gemini dense embedding with 1:1 Content/Part batching  
**Configuration:** `provider = gemini`, `model = text-embedding-004` (aliased as `gemini-embedding-2`), `dimensions = 768`  
**Variables:** batch size, truncation behavior, token usage  

**Purpose:** Establish a high-throughput, zero-cost embedding baseline for production testing.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### VECTOR-BASELINE-001

**Status:** Baseline Established (v0.3.0 / v1.0.0)  
**Strategy:** Local embedded vector storage  
**Configuration:** `provider = chroma`, `collection = knowledge_base`, `persistence = local directory`  

**Purpose:** Establish a reproducible storage baseline for local unit testing and development.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### VECTOR-BASELINE-002

**Status:** Baseline Established (v1.1.0)  
**Strategy:** Managed cloud serverless vector storage with deterministic workspace filtering  
**Configuration:** `provider = qdrant`, `collection = knowledge_base`, `filter = workspace_id`, `distance = COSINE`  

**Purpose:** Establish a scalable, multi-tenant cloud storage baseline.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### RETRIEVAL-BASELINE-001

**Status:** Baseline Established (v0.3.0 / v1.0.0 / v1.1.0)  
**Strategy:** Dense cosine semantic retrieval with Top-K cutoff  
**Configuration:** `top_k = 5`, `threshold = None`  

**Purpose:** Establish a reproducible semantic search baseline for future retrieval experiments.  
*(Comparative benchmark sweeps scheduled for v1.2).*

### RAG-BASELINE-001

**Status:** Baseline Established (v1.0.0 / v1.1.0)  
**Pipeline:** Document Indexing + Fixed Chunking + Dense Embedding + Vector Retrieval + Deterministic Context Template  
**Configuration:** `top_k = 5`, `llm_model = gemini-2.5-flash` / `gpt-4o-mini`, `rag_prompt_version = v1`  

**Purpose:** Establish a reproducible end-to-end RAG baseline before optimization experiments.  
*(Canonical v1.1 live baseline achieved MRR 0.9048, Hit Rate 1.0000 on 7 cases).*

### EXP-V12-INPUT-FORMAT-001

**Status:** Completed (2026-10-14)
**Title:** Controlled Gemini Embedding 2 Asymmetric Input Formatting Experiment
**Strategy:** Compare raw-text inputs (Control) vs Google's documented asymmetric textual formatting (Treatment)
**Configuration:**
- Embedding Model: `gemini-embedding-2` (768 dimensions, cosine similarity)
- Control: Raw query `{query}` and raw chunk `{chunk}` in Qdrant collection `kip_eval_v1_2_control`
- Treatment: Query `task: question answering | query: {query}` and chunk `title: none | text: {chunk}` in Qdrant collection `kip_eval_v1_2_formatted`
- API Constraint: `task_type` is unsupported by `gemini-embedding-2`; textual prefixes used exclusively
- Corpus & Benchmark: 18 reference documents (`benchmarks/corpus_v1_2/`) and 25 labelled queries (`benchmarks/kip_v1_2_benchmark.json`)

**Measured Results:**
- Control: Hit Rate@1 = 0.8400, Hit Rate@3 = 1.0000, Hit Rate@5 = 1.0000, MRR = 0.9133, Mean Latency = 556.89 ms
- Treatment: Hit Rate@1 = 0.8400, Hit Rate@3 = 1.0000, Hit Rate@5 = 1.0000, MRR = 0.9133, Mean Latency = 536.51 ms
- Paired Deltas: 23/25 queries unchanged in rank (92%), 1 improved (`v12-017`: rank 2 -> rank 1), 1 degraded (`v12-010`: rank 1 -> rank 2). Net MRR delta = +0.0000.
- Artifacts: [`benchmarks/kip_v1_2_formatting_control_20261014_094111.json`](../benchmarks/kip_v1_2_formatting_control_20261014_094111.json), [`benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json`](../benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json)

**Outcome & Engineering Decisions:**
1. **Raw-Text Default Preserved:** Due to exactly neutral retrieval performance, raw-text embedding remains the production default, avoiding prefix token overhead.
2. **Formatter Extension Hooks:** Provider-neutral `doc_formatter` in `EmbeddingService` and `query_formatter` in `RetrievalService` remain in the codebase for future experimentation.
3. **Pilot Scope & Qualifications:** The evaluation covers 25 queries and 18 documents. Hit Rate@3 and Hit Rate@5 saturated at 1.0000 on this pilot; results do not establish general retrieval superiority. The ~20 ms latency difference is within normal network variance and not claimed as statistically meaningful.
4. **Expanded Benchmark Built:** A 50-document / 80-case expanded benchmark was subsequently constructed to provide a more discriminative evaluation surface for subsequent hybrid and reranking experiments.

---

### EXP-V12-EXPANDED-BASELINE-001

**Status:** Completed (2026-10-14)  
**Title:** v1.2 Expanded Dense Retrieval Baseline  
**Strategy:** Dense cosine retrieval with fixed-size chunking (`chunk_size=1000, overlap=200`) against 50-document corpus  
**Run ID:** `02d492c76c7343aaaeb78506fa4b0395`  
**Artifacts:** [`benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json`](../benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json), [`docs/evaluation/v1.2_failure_analysis.md`](evaluation/v1.2_failure_analysis.md)

**Measured Results (80 cases, 50 documents):**

| Category | Cases | MRR | Hit@1 | Hit@3 | Hit@5 |
|---|---:|---:|---:|---:|---:|
| `multi_concept` | 16 | **1.0000** | 1.0000 | 1.0000 | 1.0000 |
| `paraphrase` | 16 | **0.9375** | 0.9375 | 0.9375 | 0.9375 |
| `exact_terminology` | 16 | **0.7938** | 0.6875 | 0.8750 | 0.9375 |
| `cross_document` | 8 | **0.7500** | 0.6250 | 0.8750 | 0.8750 |
| `boundary_handling` | 8 | **0.5250** | 0.3750 | 0.6250 | 0.7500 |
| `hard_negative` | 16 | **0.4427** | 0.3125 | 0.5625 | 0.6875 |
| **Overall** | **80** | **0.7623** | **0.6875** | **0.8375** | **0.8750** |

P95 query latency: 643.0 ms. This is the **frozen control baseline** for all v1.2 candidate experiments.

---

### EXP-V12-CROSS-ENCODER-001

**Status:** Completed — **REJECTED** (2026-10-14)  
**Title:** Controlled Cross-Encoder Reranking Experiment  
**Strategy:** Dense top-20 candidate retrieval followed by `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX reranker to produce final top-5  
**Artifact:** [`benchmarks/kip_v1_2_reranking_treatment_20261014_115445.json`](../benchmarks/kip_v1_2_reranking_treatment_20261014_115445.json)  
**Report:** [`docs/evaluation/v1.2_cross_encoder_experiment.md`](evaluation/v1.2_cross_encoder_experiment.md)

**Measured Results (80 cases):**
- Overall MRR: **0.7762** (+0.0140 vs control 0.7623) — **Failed primary target (≥ 0.8500)**
- `hard_negative` MRR: **0.4344** — **Failed secondary target (≥ 0.6500)**
- `multi_concept` MRR: **0.9062** — **Failed safety invariant (must be 1.0000)**
- P95 Latency: **1,691.5 ms** (+1,048.5 ms) — **Triggered rejection guardrail (> +300 ms)**

**Decision:** REJECTED. The MS MARCO cross-encoder introduced severe latency overhead (+1,048 ms P95), regressed `paraphrase` MRR (0.9375 → 0.7854), and violated the `multi_concept` safety invariant. No production integration.

---

### EXP-V12-HYBRID-RETRIEVAL-001

**Status:** Completed — **REJECTED** (2026-10-14)  
**Title:** Controlled Hybrid BM25 + Dense Retrieval with Reciprocal Rank Fusion  
**Strategy:** BM25 sparse retrieval fused with Gemini dense retrieval via RRF (k=60), deduplication, top-5 final  
**Artifact:** [`benchmarks/kip_v1_2_hybrid_treatment_20261014_121435.json`](../benchmarks/kip_v1_2_hybrid_treatment_20261014_121435.json)  
**Report:** [`docs/evaluation/v1.2_hybrid_retrieval_experiment.md`](evaluation/v1.2_hybrid_retrieval_experiment.md)

**Measured Results (80 cases):**
- Overall MRR: **0.6554** (-0.1069 vs control 0.7623) — **Failed primary target (≥ 0.8200)**
- `multi_concept` MRR: **0.8750** — **Failed safety invariant (must be 1.0000)**
- `paraphrase` MRR: **0.8281** (marginal improvement)
- P95 Latency: **670.2 ms** (+27.2 ms) — Passed guardrail

**Decision:** REJECTED. BM25 on dense technical documents with short, whole-document chunks caused severe vocabulary mismatch, harming `multi_concept` and `hard_negative` categories significantly. No production integration.

---

### EXP-V12-SENTENCE-CHUNKING-001

**Status:** Completed — **REJECTED** (2026-10-14)  
**Title:** Controlled Sentence-Boundary Chunking Experiment  
**Strategy:** `SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=150, overlap_sentences=1)` producing 173 chunks across 50 documents (3.46/doc), evaluated raw and with document-level deduplication  
**Artifact:** [`benchmarks/kip_v1_2_chunking_treatment_20261014_124804.json`](../benchmarks/kip_v1_2_chunking_treatment_20261014_124804.json)  
**Report:** [`docs/evaluation/v1.2_chunking_experiment.md`](evaluation/v1.2_chunking_experiment.md)

**Measured Results (80 cases, document-deduplicated top-5):**
- Overall MRR: **0.7471** (-0.0152 vs control 0.7623) — **Failed primary target (≥ 0.8200)**
- `exact_terminology` Hit@1: **0.8125** — Passed secondary target (≥ 0.7500)
- `boundary_handling` MRR: **0.6917** — Passed secondary target (≥ 0.6500)
- `multi_concept` MRR: **0.9688** — **Failed safety invariant (must be 1.0000)**
- `paraphrase` MRR: **0.8125** (-0.1250 vs control 0.9375) — Regression
- `hard_negative` MRR: **0.3563** (-0.0865 vs control 0.4427) — Regression
- P95 Latency: **618.6 ms** (-24.4 ms) — Passed guardrail

**Decision:** REJECTED. While sentence segmentation improves exact-terminology and boundary-handling categories, it fragments semantic context for paraphrase and multi-concept queries and fails the primary MRR target. Document-level deduplication is confirmed necessary for sub-document chunk indexing. No production integration.

**v1.2 Research Conclusion:** All four evaluated candidates failed the preregistered primary target (MRR ≥ 0.8200). The existing dense whole-document retrieval baseline (MRR 0.7623) remains the production default. Identified path forward: hierarchical parent-child chunking combined with hybrid retrieval, evaluated as a unified architecture in a future milestone.

---

## Research Themes by Project Version

The research roadmap evolves alongside the product roadmap. Each product milestone introduces opportunities to investigate specific AI systems engineering challenges.

| Product Version | Primary Research Themes | Research Status |
|-----------------|-------------------------|----------------|
| v0.1 | Documentation standards, engineering workflows, reproducibility | ✅ Completed |
| v0.2 | Backend architecture, modular software design | ✅ Completed |
| v0.3 | Document chunking, embedding strategies, vector indexing | ✅ Completed |
| v1.0 | RAG pipeline, prompt engineering, evaluation harness (`runner.py`) | ✅ Completed |
| v1.1 | Multi-tenant vector filtering (Qdrant), Gemini batching, user feedback persistence | ✅ Completed |
| v1.2 | Embedding formatting (neutral); cross-encoder reranking (rejected); hybrid BM25+dense RRF (rejected); sentence-boundary chunking (rejected) — dense whole-document retrieval retained as production default | ✅ Research Complete — All Candidates Rejected |
| v1.3 | Performance optimization, caching, latency profiling, observability | 📅 Planned → Deferred |
| v2.0 | Conversational memory, long-term memory architectures | 📅 Planned → Deferred |
| v2.1 | Tool calling, API orchestration, workflow reliability | 📅 Planned → Deferred |
| v2.2 | Planning algorithms, autonomous agents, multi-step reasoning | 📅 Planned → Deferred |
| v2.3 | Knowledge synthesis, explainability, intelligent orchestration | 📅 Planned → Deferred |
| v2.4 | Knowledge graphs, entity linking, graph-based retrieval | 📅 Planned → Deferred |
| v3.0 | Multimodal retrieval, multimodal reasoning, unified knowledge representation | 📅 Planned → Deferred |
| v3.1 | Collaboration systems, access control, collaborative AI workflows | 📅 Planned → Deferred |
| v3.2 | Cloud deployment, distributed systems, operational AI | 📅 Planned → Deferred |
| v4.0 | Enterprise AI systems, scalability, governance, security | 📅 Planned → Deferred |

Every major product release should include at least one research question, one benchmark, and documented experimental findings.

---

## Expected Research Outputs

The project aims to generate practical research artifacts throughout its lifecycle. These outputs provide evidence of engineering progress and create opportunities for knowledge sharing.

Expected outputs include:

### Technical Reports

- Architecture evaluations
- Retrieval performance studies
- Memory system evaluations
- Agent workflow analyses
- Knowledge graph experiments

### Benchmark Reports

- Retrieval benchmarks
- Response quality evaluations
- Performance comparisons
- Scalability analyses
- Version-to-version benchmark reports

### Engineering Documentation

- Design decisions
- Architecture evolution
- Experiment reports
- Benchmark methodologies
- Lessons learned

### Open-Source Contributions

- Reusable AI engineering components
- Benchmark datasets
- Evaluation utilities
- Documentation templates
- Best practices

### Academic Opportunities

Where appropriate, mature research outcomes may be developed into:

- Conference papers
- Workshop papers
- Technical articles
- Blog posts
- Public presentations

Publication is considered an optional outcome rather than the primary objective. The primary goal remains improving the engineering quality of the platform through systematic experimentation.

---

## Document Governance

| Item | Value |
|------|-------|
| Document Owner | Project Maintainer |
| Project | Knowledge Intelligence Platform |
| Document Version | 2.1 |
| Project Version | v1.2 (Research Phase — Experiments Complete) |
| Status | Active — v1.2 Research Concluded |
| Last Reviewed | 2026-10-14 |

### Review Policy

This document should be reviewed whenever significant research directions, evaluation methodologies, or experimentation strategies change.

Research themes may evolve as the platform matures, but updates should remain aligned with the Vision document and Product Roadmap.

All research activities should prioritize reproducibility, transparency, and measurable engineering impact.