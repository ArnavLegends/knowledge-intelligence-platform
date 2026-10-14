# KIP Expanded Evaluation Corpus — v1.2 Large Benchmark

## Purpose

This directory contains the expanded 50-document reference corpus used for large-scale, discriminative
retrieval evaluation in KIP v1.2. It expands the previous 18-document pilot to eliminate top-3 and top-5
hit rate saturation and provide challenging, realistic distractor environments.

## Corpus Structure & Breakdown

- **Total Documents:** 50 files (LF line endings only).
- **Genuine KIP Architectural Documents:** 38 documents covering multitenancy, ingestion, vector store adapters, Qdrant/Chroma internals, Gemini/OpenAI providers, RAG prompting, feedback webhooks, and evaluation models.
- **Targeted Hard Negatives & Semantic Distractors:** 12 documents containing overlapping terminology (BM25, rerankers, semantic chunking, Redis caching, conversational memory, Neo4j, agents, OAuth2, WebSockets) representing deferred or unadopted architectures.
- **Candidate Chunks:** Exactly 50 chunks (1 chunk/document at 1000/200 character chunking). Top-5 retrieval evaluates 10% of the corpus; Top-10 retrieval evaluates 20% of the corpus.

## Corpus Documents Table

| File | Size (bytes) | Document ID | Topic Domain |
|------|-------------|-------------|--------------|
| distractor_agentic_tool_calling.txt | 730 | 719be3bc1a65bf1668c556088b9e52c3b053b8d5ceed43ba3a53c07664235bbd | Semantic Distractor / Hard Negative |
| distractor_alternative_chunkers.txt | 823 | eb7328c9548152284ee036160852db349e8870efedb702bc30c257bf0ce85a46 | Semantic Distractor / Hard Negative |
| distractor_cohere_reranking_pipeline.txt | 746 | c88c2e952b78fb0c59828144a2f6dc31066b9d40fdfd0cf64cf455e05aed6d6f | Semantic Distractor / Hard Negative |
| distractor_conversational_memory_store.txt | 726 | 4a43847e0a59e1f0a140670fe9f2835d650d01777f068c7059ca4dde01d297c7 | Semantic Distractor / Hard Negative |
| distractor_external_judge_evaluators.txt | 847 | b97ea6a6da102ef23eb0f738d9a3e3d9a90e52d9c6e500bbafc83ec8cdf26827 | Semantic Distractor / Hard Negative |
| distractor_hybrid_search_proposals.txt | 837 | 983d6d8c567def41851d81b22bfd11101162c756df71d44c203c7ea127fffebc | Semantic Distractor / Hard Negative |
| distractor_kubernetes_cluster_orchestration.txt | 730 | 605674cad36b6932f295624278decc6b869979d13d6d01d93d584d8da4e4d5ce | Semantic Distractor / Hard Negative |
| distractor_legacy_chroma_settings.txt | 717 | 2052e898f98dfaa9a756da58babe0543d21bc43aa64a3382b62699bfaf2b4f0e | Semantic Distractor / Hard Negative |
| distractor_neo4j_knowledge_graph.txt | 742 | 5273133127acb88c5ba1cf3ca6bd52ee54dbb5b258bb4942d09cc99fc72cc708 | Semantic Distractor / Hard Negative |
| distractor_oauth2_sso_authentication.txt | 743 | cc186008312a98203efe9c33acb60fbcf962447efc3af900fbbc0830d2f5a35c | Semantic Distractor / Hard Negative |
| distractor_redis_caching_architecture.txt | 810 | f9ff823a7997421940062d0860e452d9aa3041b0143541f38aa42d85766280fa | Semantic Distractor / Hard Negative |
| distractor_streaming_websocket_rag.txt | 728 | 49df4a8ebbf6953363e21ff7d77c48d3d0facf726f03230475a98156e09f9179 | Semantic Distractor / Hard Negative |
| kip_api_specifications.txt | 843 | 82ddbc93b8ada53f638e7f19172b9db774b8b0c943d5f057257c0a9b25bf77c5 | Core KIP Architecture |
| kip_batch_ingestion_limits.txt | 801 | 99e284eeccd19425ddfa9ce3b3b56aee093a00e21115b1c1811f4f226658ff61 | Core KIP Architecture |
| kip_benchmark_dataset_schema.txt | 813 | a1308d724380a1c00c0d93729f1230521ade1678b094587506576c6a1db23d52 | Core KIP Architecture |
| kip_chroma_provider_internals.txt | 823 | dd1062cdcdf97d941f0c469d35c50f00911dc3c237a6d5d58e05b4abe180f607 | Core KIP Architecture |
| kip_chunk_metadata_provenance.txt | 854 | 860245a0c6c64c5eced3a001fc624234945d7021b99cfb90c17f03e12933d08a | Core KIP Architecture |
| kip_chunking_and_embeddings.txt | 812 | d5bb2146121b7983b9a12fb4f2bea7e765657a49ef763845b8a4d258aec8f7c5 | Core KIP Architecture |
| kip_cold_start_mitigation.txt | 831 | eb66b55f0ac4d316a63501580bd58de644dddef365851aadbdc184a8450639e4 | Core KIP Architecture |
| kip_configuration_settings.txt | 847 | 7fef86ca551535b7734af4a1936fd691ee0c8066411060465e217e82252fc140 | Core KIP Architecture |
| kip_docker_and_deployment.txt | 734 | 85844219742c280e2fa111770f6179e0fe8cf4f1bd67fff3d6cb4c2296f018a3 | Core KIP Architecture |
| kip_document_parsers.txt | 812 | 4fbdf23f18ad0ac98c6399beb1685504c99a817d37127a3a035e1aebe0f290f9 | Core KIP Architecture |
| kip_docx_parser_internals.txt | 843 | 13bcf306cda2e63a1006c0e6e4636009d64611eba82c91923337fb669677a79b | Core KIP Architecture |
| kip_embedding_manager.txt | 844 | b419750e3e13f00a867232f3480a00e675d0e87a21b81c95e7c2d0b4779d9e14 | Core KIP Architecture |
| kip_empty_context_guard.txt | 812 | e20250354884e429019e726075b2ff761c6640afdb45ad1c21d43b5a1fda7836 | Core KIP Architecture |
| kip_error_handling_protocols.txt | 820 | cba1b60df81cc05102c55c065ac08a952ba7521b8f6c3839ebfb877af44c772c | Core KIP Architecture |
| kip_evaluation_framework.txt | 866 | 33f5341a76abe7abad9ec92cafb5cc73be29bda23000d5e06fb6af35b59008e8 | Core KIP Architecture |
| kip_evaluation_workspace_isolation.txt | 832 | 5a158d5895fd470945075400f063cb5c1fa98cba1505e3e115ae5326f8d7127b | Core KIP Architecture |
| kip_feedback_token_security.txt | 782 | 10fd50444d1f061419ceab7ca1fcf953c85d7e0e5ca1e5ed5c2454dc6c36197a | Core KIP Architecture |
| kip_feedback_webhook.txt | 785 | c94143ee63b68e97f2dd58bab327285a1152843f67a1636ade5b91d86ced9074 | Core KIP Architecture |
| kip_gemini_embedding_provider.txt | 825 | 211adde2b71f8a8e42f4979d234681d7caeba21dc429acc6d93dac860657f806 | Core KIP Architecture |
| kip_ground_truth_derivation.txt | 839 | d741eb22e0b69fdb3b3f249618771d02171b4bc1ed43a09ac0fbc21190ccdb46 | Core KIP Architecture |
| kip_grounded_rag_prompting.txt | 826 | a69f55b648c0d0d7eb2420cf877606ef6ac0300dd60bcfd06b7558cc741a1aa9 | Core KIP Architecture |
| kip_idempotency_service.txt | 839 | 52d4987e73b9984814b2f7314430103c12cbfcf69d433309a93ccefa126c625e | Core KIP Architecture |
| kip_llm_gateway.txt | 777 | 7814e557c2f42e3801fd958cfa580d3964bae3567ebe81d008d227f39ce4e843 | Core KIP Architecture |
| kip_multitenancy_architecture.txt | 860 | f0ecc88754c5bb06bae3d49716ce1f2ee0befe74adaceb859a2d3017f61470e3 | Core KIP Architecture |
| kip_openai_embedding_provider.txt | 790 | 8ef389f4896c6097d3fdbda82fdfbfe74e1343ee51ceb2ee52c27a8b5a08500e | Core KIP Architecture |
| kip_openai_llm_provider.txt | 786 | 89ac20511510f46dddb54d94c939f8cceea2521cdff31deb3107e70b75a9e4e3 | Core KIP Architecture |
| kip_overview.txt | 893 | 07123957b17b180eef3505c6b2dc1f76a161cedcc618081eb882de99dbf2a324 | Core KIP Architecture |
| kip_paired_experiment_protocol.txt | 862 | adf82ba374b87a4def586e51e84b0572732495fc15eff0bc980bd5e659286639 | Core KIP Architecture |
| kip_pdf_parser_internals.txt | 860 | 3f61e52aea163d310e47016c89f60d93006eef4fe7a5f6bfde9ccc5e36e1685e | Core KIP Architecture |
| kip_provenance_attribution.txt | 840 | 8ac34d311cee845e8b56370230ae7101e45dcf14085e15d0a99c4b1889a22877 | Core KIP Architecture |
| kip_qdrant_provider_internals.txt | 841 | fcf8d7a92b7a1afaa6563c14e01cd1b77aadd4b0ee4fd1ffc5bbdc69ed60d4f7 | Core KIP Architecture |
| kip_rag_service_orchestration.txt | 799 | 6c61b0b1da2718bc478cfa0b540be731c390541357bd78ae08486528a4996cc2 | Core KIP Architecture |
| kip_retrieval_and_rag.txt | 874 | 423a09a2d8b079bb55b4663e0e9ae7846e7d90f80f1bb54db20030a98067f538 | Core KIP Architecture |
| kip_retrieval_metrics_definitions.txt | 837 | 949d52cb6ed7148e01009c8b5246331d0aebadebae534dd28128e391db5147f6 | Core KIP Architecture |
| kip_security_threat_model.txt | 886 | 7c2e66d00531cb18f524ec1161705f3945812b6de08f511789d896a70efa3d2f | Core KIP Architecture |
| kip_streamlit_frontend_state.txt | 808 | 5ed26ebb9d3c7ad93aff533cc2fabc7ad32ac113ec48b648fb0406bb8ce2d99f | Core KIP Architecture |
| kip_streamlit_ui_components.txt | 840 | 252d1bbb10d93bfad68acd919930a4b217ba92ac42a52626b225c20bb35391ba | Core KIP Architecture |
| kip_vector_store_adapters.txt | 816 | 1b9edfe7492b4a9eaa4eb09b14f5eeb358d5e0fe41b8dae1af8868fd02b8a12a | Core KIP Architecture |

## Line Ending & Hash Stability Invariant

All corpus documents use Unix LF (\n) exclusively. Any CR byte alters raw file bytes and breaks ground-truth document IDs.
