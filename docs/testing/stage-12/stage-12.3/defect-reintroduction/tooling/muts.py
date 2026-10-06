# Mutation catalogue for the 6.6 defect-reintroduction proof.
# kind: "primary" = reintroduces the closed defect at its fix site;
#       "probe"   = an additional realistic regression of the same issue, used to look for guard gaps.

SBQ_DB = ["-k", "not end_to_end and not manuscript_a and not manuscript_b"]  # 3 DB-backed tests; no DB available

MUTATIONS = [
    # ── Phase 2 ──────────────────────────────────────────────────────────────
    dict(id="P2-02-plot-hole-coercion", issue="P2-2", kind="primary",
         file="backend/services/ai_service.py",
         desc="coerce_plot_hole_result made all-or-nothing again: one malformed finding (non-object or no description) "
              "discards the whole response instead of salvaging the usable findings (pre-3.4 hard-fail on invalid AI output)",
         tests=["tests/test_extract_json_audit.py"],
         edits=[(
             '        if not isinstance(item, dict):\n'
             '            discarded += 1\n'
             '            continue\n'
             '        description = str(item.get("description") or "").strip()\n'
             '        if not description:\n'
             '            discarded += 1\n'
             '            continue\n'
             '        severity = str(item.get("severity") or "").lower()\n'
             '        kept.append({\n'
             '            "issue_id":',
             '        if not isinstance(item, dict):\n'
             '            return None, 0  # REINTRODUCED P2-2: one malformed finding fails the whole response\n'
             '        description = str(item.get("description") or "").strip()\n'
             '        if not description:\n'
             '            return None, 0  # REINTRODUCED P2-2\n'
             '        severity = str(item.get("severity") or "").lower()\n'
             '        kept.append({\n'
             '            "issue_id":')]),
    dict(id="P2-02b-extract-json-repair", issue="P2-2", kind="probe",
         file="backend/services/ai_service.py",
         desc="_extract_json JSON-repair step broken: the balanced-brace span extraction (JSON embedded in prose / "
              "after a preamble) is removed, so only bare or fenced JSON parses",
         tests=["tests/test_extract_json_audit.py"],
         probes=[["tests/test_degraded_output.py", "tests/test_generation_limits.py"]],
         edits=[(
             '    for span in _balanced_json_spans(stripped) + _balanced_json_spans(text):\n'
             '        if span not in candidates:\n'
             '            candidates.append(span)\n',
             '    pass  # REINTRODUCED P2-2 probe: no balanced-span repair\n')]),
    dict(id="P2-04-voice-intent-silent-guess", issue="P2-4", kind="primary",
         file="backend/services/voice/intent.py",
         desc="voice intent.classify reverted to the pre-3.6 silent fallback: raw _complete + _extract_json(raw, fallback={}) "
              "so an unreadable classification becomes a repaired guess at confidence 0.4 instead of an honest failure",
         tests=["tests/test_voice_execution.py"],
         edits=[(
             '    data, meta = await complete_structured(\n'
             '        _SYSTEM, user, coerce=coerce_intent,\n'
             '        temperature=0.0, max_tokens=300, label="voice_intent",\n'
             '    )\n'
             '    if data is None:\n'
             '        logger.warning("[voice.intent] stage=classify outcome=unreadable candidates=%d",\n'
             '                       len(cand_names))\n'
             '        return DetectedIntent("none", "", 0.0, {}, cand_names,\n'
             '                              "classification could not be read")\n',
             '    from services.ai_service import _complete, _extract_json  # REINTRODUCED P2-4\n'
             '    raw = await _complete(_SYSTEM, user, temperature=0.0, max_tokens=300)\n'
             '    data = _extract_json(raw, fallback={})\n')]),
    dict(id="P2-05-voice-false-success", issue="P2-5", kind="primary",
         file="backend/services/voice/lifecycle.py",
         desc="derive_command_status reports a dispatched-but-unexecuted plan (READY/PLANNED nodes) as SUCCEEDED — "
              "the original 'success at plan time' defect",
         tests=["tests/test_voice_execution.py", "tests/test_voice_unit.py"],
         pytest_args=["-k", "not test_planner_drops_invalid_capability"],  # reaches the live model via unstubbed _complete_ex
         edits=[(
             '        return EXECUTING          # dispatched, outcome not yet reported',
             '        return SUCCEEDED          # REINTRODUCED P2-5: dispatched == done')]),
    dict(id="P2-08-bible-status-integrity", issue="P2-8", kind="primary",
         file="backend/routers/story_bible.py",
         desc="derive_status returns STATUS_COMPLETED unconditionally (pre-3.2): a bible whose sections failed/were "
              "truncated/empty still reports 'completed'",
         tests=["tests/test_story_bible_outcomes.py", "tests/test_story_bible_quality.py"], pytest_args=SBQ_DB,
         edits=[(
             '    if not outcomes:\n'
             '        return STATUS_FAILED\n'
             '    generated = sum(1 for o in outcomes if o.ok)\n',
             '    return STATUS_COMPLETED  # REINTRODUCED P2-8: unconditional completed\n'
             '    generated = sum(1 for o in outcomes if o.ok)\n')]),
    dict(id="P2-08b-bible-grounding-rules", issue="P2-8", kind="primary",
         file="backend/services/ai_service.py",
         desc="generate_story_bible_section grounding rules removed (pre-3.3): no 'cite the source tag' rule, no "
              "BIBLE_NOT_ESTABLISHED way to decline, no 'never state anything you cannot attribute' — only the bare "
              "'do not invent' instruction that produced the hallucinated bible",
         tests=["tests/test_story_bible_outcomes.py", "tests/test_story_bible_quality.py"], pytest_args=SBQ_DB,
         edits=[(
             '        "Every entry in the context is tagged with its source, like [Ch 7] or "\n'
             '        "[Character: Devika Rao].\\n"\n'
             '        "RULES:\\n"\n'
             '        "1. Cite the source tag for every factual statement, in this shape (a placeholder, not "\n'
             '        "content to copy): \\"<a statement from the story> [Ch N]\\".\\n"\n'
             '        f"2. If the manuscript does not establish something, write exactly "\n'
             '        f"\\"{BIBLE_NOT_ESTABLISHED}\\" instead of guessing or filling the gap.\\n"\n'
             '        "3. Never state anything you cannot attribute to a tag shown in the context.\\n"\n'
             '        "4. If the context says material is missing, do not describe that material."\n',
             '        ""  # REINTRODUCED P2-8: grounding RULES block removed\n')]),
    dict(id="P2-09-hint-reconcile-noop", issue="P2-9", kind="primary",
         file="backend/services/character_names.py",
         desc="resolve_hints_for_names made a no-op: registering/confirming a character never dismisses the matching "
              "unrecognised-name hint (the original 'nothing made that decision' defect)",
         tests=["tests/test_character_hint_sync.py"],
         edits=[(
             '    if not targets:\n'
             '        return []\n'
             '\n'
             '    live = (',
             '    return []  # REINTRODUCED P2-9: reconciliation never dismisses anything\n'
             '\n'
             '    live = (')]),
    dict(id="P2-09b-create-character-wiring", issue="P2-9", kind="probe",
         file="backend/routers/characters.py",
         desc="create_character no longer calls resolve_hints_for_names (router wiring removed; service left intact) — "
              "a hand-added character stays in the unrecognised list",
         tests=["tests/test_character_hint_sync.py"],
         edits=[(
             '    dismissed = resolve_hints_for_names(db, story_id, names_of(character))\n',
             '    dismissed = []  # REINTRODUCED P2-9 probe: create no longer reconciles hints\n')]),
    dict(id="P2-12-outline-beats-field", issue="P2-12", kind="primary",
         file="frontend/components/ai-tools/AIToolsSidebar.tsx",
         desc="scene-outline UI reads res.data.beats again (backend returns `outline`) — outline renders nothing",
         tests=["tests/test_generation_limits.py"],
         edits=[("      setBeats(res.data.outline ?? [])", "      setBeats(res.data.beats ?? [])  // REINTRODUCED P2-12")]),
    dict(id="P2-12b-retrieval-query-kwarg", issue="P2-12/P2-13", kind="probe",
         file="backend/routers/writing_tools.py",
         desc="PRE-1 root cause restored: writing_tools calls retrieve_relevant_chunks(query=...) instead of question= "
              "(TypeError at runtime -> outline/continuation fail)",
         tests=["tests/test_generation_limits.py"],
         probes=[["tests/test_retrieval_signatures.py"]],
         edits=[("    story_summaries = await retrieve_relevant_chunks(\n        question=tail_trimmed,\n",
                 "    story_summaries = await retrieve_relevant_chunks(\n        query=tail_trimmed,  # REINTRODUCED PRE-1\n")]),
    dict(id="P2-13-continuation-token-budget", issue="P2-13", kind="primary",
         file="backend/services/ai_service.py",
         desc="continuation max_tokens fixed at 1600 regardless of requested length (pre-3.1) — Long truncates",
         tests=["tests/test_generation_limits.py"],
         edits=[("    max_tokens = max(1600, int(3 * continuation_length * 1.9) + 400)",
                 "    max_tokens = 1600  # REINTRODUCED P2-13")]),
    dict(id="P2-14-continuity-silent-all-clear", issue="P2-14", kind="primary",
         file="backend/services/ai_service.py",
         desc="check_continuity reverted to raw _complete + _extract_json(raw, fallback=[]) — unreadable model output "
              "becomes an empty list, i.e. a false 'no contradictions found'",
         tests=["tests/test_extract_json_audit.py", "tests/test_continuity_citation_validation.py"],
         edits=[(
             '    issues, meta = await complete_structured(\n'
             '        system, user,\n'
             '        coerce=coerce_continuity_issues,\n'
             '        temperature=0.1,\n'
             '        max_tokens=1200,\n'
             '        label="continuity",\n'
             '    )\n',
             '    raw = await _complete(system, user, temperature=0.1, max_tokens=1200)  # REINTRODUCED P2-14\n'
             '    issues = _extract_json(raw, fallback=[])\n'
             '    meta = DegradedMeta(False, None, 1, 0)\n')]),
    dict(id="P2-14b-continuity-failure-not-flagged", issue="P2-14", kind="probe",
         file="backend/services/ai_service.py",
         desc="check_continuity keeps the structured contract but reports an unreadable response as a clean, "
              "non-degraded empty result (false all-clear via the meta instead of via the parser)",
         tests=["tests/test_extract_json_audit.py", "tests/test_continuity_citation_validation.py"],
         probes=[["tests/test_degraded_output.py"]],
         edits=[(
             '        return [], DegradedMeta(\n'
             '            True,\n'
             '            "Some of this manuscript could not be checked — the AI response could "\n'
             '            "not be read. Please run the check again.",\n'
             '            meta.attempts, 0,\n'
             '        )\n',
             '        return [], DegradedMeta(False, None, meta.attempts, 0)  # REINTRODUCED P2-14 probe\n')]),
    # ── Stage 5 (task granularity) ───────────────────────────────────────────
    dict(id="S5-5.1-version-label-only", issue="Stage 5 task 5.1", kind="primary",
         file="backend/services/prompt_registry.py",
         desc="resolve_prompt_version always runs the fallback's builder but reports the requested version — the "
              "version becomes a logged label, not actual prompt content",
         tests=["tests/test_prompt_registry.py"],
         edits=[("    entry = PROMPT_REGISTRY.get(version)\n",
                 "    entry = PROMPT_REGISTRY.get(fallback)  # REINTRODUCED 5.1: label-only versioning\n")]),
    dict(id="S5-5.3-name-preservation-check", issue="Stage 5 task 5.3", kind="primary",
         file="backend/services/transform_preservation.py",
         desc="check_character_name_preservation never reports a dropped character name (the deterministic "
              "preservation check is neutralised, so the repair-retry never fires)",
         tests=["tests/test_transform_preservation.py"],
         edits=[("            violations.append(c.name)\n",
                 "            pass  # REINTRODUCED 5.3: dropped names never reported\n")]),
    dict(id="S5-5.4-lock-byte-identity", issue="Stage 5 task 5.4", kind="primary",
         file="backend/services/transform_preservation.py",
         desc="reconstruct_with_locks trusts the model's echo of each [KEEP] segment instead of splicing the original "
              "captured bytes — locked sentences can be silently rewritten",
         tests=["tests/test_transform_preservation.py"],
         edits=[(
             '    rewrite_iter = iter(model_rewrites)\n'
             '    out_parts = []\n'
             '    for s in segments:\n'
             '        if s["locked"]:\n'
             '            out_parts.append(s["text"])  # original bytes, never the model\'s echo\n',
             '    rewrite_iter = iter(model_rewrites)\n'
             '    keep_iter = iter(_re.findall(r"\\[KEEP\\](.*?)\\[/KEEP\\]", model_output, _re.DOTALL))\n'
             '    out_parts = []\n'
             '    for s in segments:\n'
             '        if s["locked"]:\n'
             '            out_parts.append(next(keep_iter, s["text"]))  # REINTRODUCED 5.4: trusts model echo\n')]),
    dict(id="S5-5.6-strength-proxy", issue="Stage 5 task 5.6", kind="primary",
         file="backend/services/transform_preservation.py",
         desc="check_strength_violation never flags a 'light' edit, whatever the sentence-count change (strength "
              "control has no deterministic ceiling)",
         tests=["tests/test_transform_preservation.py"],
         edits=[("        return abs(_count_sentences(original) - _count_sentences(transformed)) > 1\n",
                 "        return False  # REINTRODUCED 5.6: light strength never flagged\n")]),
    dict(id="S5-5.11-glossary-consistency", issue="Stage 5 task 5.11", kind="primary",
         file="backend/services/transform_preservation.py",
         desc="check_translation_name_consistency ignores the glossary: a name correctly transliterated per the "
              "approved glossary is flagged missing (byte-identity semantics wrongly applied to translation)",
         tests=["tests/test_transform_preservation.py"],
         edits=[("        if translated_name in transformed or source_name in transformed:\n",
                 "        if source_name in transformed:  # REINTRODUCED 5.11: glossary form not accepted\n")]),
    dict(id="S5-5.13-priority-sort", issue="Stage 5 task 5.13", kind="primary",
         file="backend/services/ai_service.py",
         desc="coerce_writing_suggestions no longer orders suggestions high > medium > low (model's arbitrary order returned)",
         tests=["tests/test_suggestions_priority.py"],
         edits=[('    kept.sort(key=lambda s: order.get(s["priority"], 1))\n',
                 '    pass  # REINTRODUCED 5.13: no priority ordering\n')]),
    dict(id="S5-5.14-continuity-tier1", issue="Stage 5 task 5.14", kind="primary",
         file="backend/services/ai_service.py",
         desc="validate_continuity_citations Tier-1 existence check removed: findings citing fabricated / out-of-range "
              "chapters are kept",
         tests=["tests/test_continuity_citation_validation.py", "tests/test_manuscript_report_citations.py"],
         edits=[("        if not refs or not all(r in real_chapter_numbers for r in refs):\n",
                 "        if not refs:  # REINTRODUCED 5.14: fabricated chapter refs accepted\n")]),
    dict(id="S5-5.14b-report-citations", issue="Stage 5 task 5.14", kind="primary",
         file="backend/services/ai_service.py",
         desc="validate_manuscript_report_citations._valid accepts every chapter reference, so fabricated chapters "
              "survive in arcs/pacing/threads/strengths/improvements/themes",
         tests=["tests/test_continuity_citation_validation.py", "tests/test_manuscript_report_citations.py"],
         edits=[("        return [r for r in (refs or []) if r in chapter_numbers]\n",
                 "        return list(refs or [])  # REINTRODUCED 5.14: no existence check\n")]),
    dict(id="S5-5.15-syllable-count", issue="Stage 5 task 5.15", kind="primary",
         file="backend/services/analytics_service.py",
         desc="_count_syllables back to vowel-LETTER counting (old frontend regex): 'queue' scores 4, skewing readability",
         tests=["tests/test_analytics_service.py"],
         edits=[("    groups = _VOWEL_GROUP_RE.findall(word)\n",
                 '    groups = re.findall(r"[aeiouy]", word.lower())  # REINTRODUCED 5.15: vowel letters\n')]),
]

MUTATIONS.append(dict(
    id="P2-10-notes-duplicated-in-plan", issue="P2-10", kind="primary", runner="playwright-unit",
    file="frontend/app/(dashboard)/projects/[id]/plan/page.tsx",
    desc="Notes re-mounted as a 'Notes' section of the Plan workspace (it also lives in World) — the pre-8.8 "
         "duplicated-across-navigation state",
    tests=["tests/tool-homes.spec.ts"],
    edits=[
        ("const PacingGoalPanel = dynamic(() => import('@/components/pacing/PacingGoalPanel'), { ssr: false })\n",
         "const PacingGoalPanel = dynamic(() => import('@/components/pacing/PacingGoalPanel'), { ssr: false })\n"
         "const NotesPanel = dynamic(() => import('@/components/notes/NotesPanel'), { ssr: false })  // REINTRODUCED P2-10\n"),
        ("  { id: 'pacing', label: 'Pacing', icon: Target },\n",
         "  { id: 'pacing', label: 'Pacing', icon: Target },\n"
         "  { id: 'notes', label: 'Notes', icon: Target },\n"),
        ("        {section === 'pacing' && <PacingGoalPanel storyId={storyId} />}\n",
         "        {section === 'pacing' && <PacingGoalPanel storyId={storyId} />}\n"
         "        {section === 'notes' && <NotesPanel storyId={storyId} />}\n"),
    ]))

# Supplementary: P2-1 / P2-11 are mapped only to the LIVE browser spec, but the same ownership rule is unit-tested
# (not listed in the traceability table) by frontend/tests/selection-ownership.spec.ts. Same mutations as the
# browser-prepared patches, run against that deterministic spec.
MUTATIONS.append(dict(
    id="P2-01u-toolbar-escape-dismiss", issue="P2-1", kind="supplementary", runner="playwright-unit",
    file="frontend/lib/selectionOwnership.ts",
    desc="resolveToolbarMode ignores `dismissed` — Escape no longer hides the toolbar (same mutation as "
         "browser-prepared/P2-01-toolbar-escape-dismiss.patch)",
    tests=["tests/selection-ownership.spec.ts"],
    edits=[("  if (input.dismissed) return 'hidden'\n",
            "  // REINTRODUCED P2-1: Escape/dismissal no longer hides the toolbar\n")]))
MUTATIONS.append(dict(
    id="P2-11u-toolbar-with-sidebar-open", issue="P2-11", kind="supplementary", runner="playwright-unit",
    file="frontend/lib/selectionOwnership.ts",
    desc="selectionOwner no longer gives the selection to the open AI sidebar — the floating toolbar shows "
         "alongside it (same mutation as browser-prepared/P2-11-toolbar-with-sidebar-open.patch)",
    tests=["tests/selection-ownership.spec.ts"],
    edits=[("  if (input.sidebarVisible) return 'sidebar'\n",
            "  // REINTRODUCED P2-11: the open AI sidebar no longer takes ownership of the selection\n")]))
