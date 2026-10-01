# Documentation tooling (task 11.8). Application build and run: see README.md.

PYTHON ?= python3

.PHONY: docs docs-check docs-paths

# Regenerate every managed Word copy from its Markdown source (needs pandoc 3.7.0.2).
docs:
	$(PYTHON) scripts/docs/sync_docs.py build

# Fail if any managed Markdown source changed without regenerating its Word copy.
docs-check:
	$(PYTHON) scripts/docs/sync_docs.py check

# Fail if an active document names a repository file that does not exist.
docs-paths:
	$(PYTHON) scripts/docs/check_doc_paths.py
