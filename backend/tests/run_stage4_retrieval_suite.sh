#!/bin/bash
# Stage 4 task 4.15 — retrieval regression suite, local execution.
#
# CI wiring is explicitly OUT OF SCOPE here and deferred to Stage 6 task 6.1
# per approved plan correction #1 (2026-09-21): "Implement and run the
# regression suite locally as part of Stage 4 ... defer ONLY the CI wiring to
# Stage 6". This script is what task 6.1 should eventually point a CI job at.
#
# Requires: PostgreSQL + pgvector reachable via backend/.env DATABASE_URL,
# and BGE-M3 + vLLM loadable/reachable (several tests call the real LLM).
# Every fixture used is disposable and self-cleaning — safe to run repeatedly
# against a live database with real author data present; nothing here reads,
# lists, or modifies real story/chapter/character rows.
#
# Usage: cd backend && bash tests/run_stage4_retrieval_suite.sh

set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 -m pytest \
  tests/test_retrieval_scope.py \
  tests/test_recall_measurement.py \
  tests/test_plot_importance_ranking.py \
  tests/test_retrieval_vs_knowledge_failure.py \
  tests/test_chapter_arc_fields.py \
  tests/test_alias_resolution.py \
  tests/test_search_module.py \
  tests/test_semantic_dedup.py \
  tests/test_semantic_search_stability.py \
  tests/test_cast_classification_accuracy.py \
  tests/test_cast_hint_sync_integration.py \
  tests/test_character_merge.py \
  tests/test_retrieval_signatures.py \
  tests/test_extract_json_audit.py \
  -v "$@"
