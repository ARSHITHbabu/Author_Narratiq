# lxml PYSEC-2026-87 (CVE-2026-41066, XXE): reachability in NarratIQ (Stage 12.1, Gate 5)

**Advisory:** lxml before 6.1.0, used with its default parser (`resolve_entities=True`), lets untrusted XML read local files.

**Exposure:**
- NarratIQ parses author-uploaded `.docx` manuscripts with `python-docx` 1.2.0, which uses lxml 5.3.0.
- The backend has no direct lxml use (`grep -rn "lxml\|etree" backend --include=*.py`, excluding tests: none).

**Code:** both of python-docx's parsers set the safe option: `docx/oxml/parser.py:19` and `docx/opc/oxml.py:21` build `etree.XMLParser(remove_blank_text=True, resolve_entities=False)`.

**Proof (2026-10-03):**
1. A `.docx` was built whose `word/document.xml` declares `<!ENTITY x SYSTEM "file:///…/xxe-secret.txt">` and uses `&x;` in a paragraph.
2. It was opened with `docx.Document()`, the same call the import uses.
3. Result: it parsed, the paragraph text came back empty, and **the canary file's contents did not appear**.

**Classification:** not reachable through NarratIQ. A later lxml upgrade (6.1.0) is hygiene, not a fix for an exposure.
