#!/usr/bin/env python3
"""Build NarratIQ_Owner_Decision_Package.docx — the product owner's decision workbook.

Read-only with respect to the repository: it reads the master checklist at git HEAD 2b63b51
(``git show``) and writes only the .docx next to this script. It never records an owner answer.

Run with a private venv that has python-docx:
    python3 -m venv <venv> && <venv>/bin/pip install python-docx
    <venv>/bin/python build_owner_decision_package.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for clarity of layout options)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]  # .../Author_Narratiq
OUT = HERE / "NarratIQ_Owner_Decision_Package.docx"
HEAD = "2b63b51"
CHECKLIST = "docs/NarratIQ_Master_Implementation_Checklist.md"
TODAY = "2026-10-06"
BOX = "☐"  # ☐ empty ballot box — the only box glyph this document may contain
HEADER_TEXT = "NarratIQ v3.3.0 RC — Owner Decision Package"

# --------------------------------------------------------------------------------------------
# The owner-decision boxes and their exact quoted label text. "head" is the line number at HEAD 2b63b51
# (None for a box added after HEAD); every box is located in the working tree BY TEXT at build time.
# Each maps to exactly one decision ID. L3531 is closed (decided and implemented 2026-10-06).
# --------------------------------------------------------------------------------------------
BOXES = [
    # head line, exact label (substring of the box line), OD id, stage, role
    (1997, "**5.14 — Story audit: continuity false positives and reasoning depth**", "OD-01", "5", "Task 5.14 parent box"),
    (2008, "Strengthen timeline reasoning (Critical 4)", "OD-01", "5", "5.14 item (AUDIT-C4)"),
    (2009, "Strengthen narrative reasoning (Critical 5)", "OD-01", "5", "5.14 item (AUDIT-C5)"),
    (2014, "Add relationship arc analysis (Medium 11)", "OD-01", "5", "5.14 item (AUDIT-M11)"),
    (2067, "All 15 Story Audit issues closed or accepted", "OD-01", "5", "Stage 5 completion-gate line"),
    (2238, "Alert on regression beyond an agreed threshold", "OD-10", "6", "6.5 implementation item (\u2018agreed threshold\u2019)"),
    (2852, "Every deferred issue is explicitly accepted", "OD-02", "9", "9.2 verification line"),
    (2855, "**9.3 — Performance testing**", "OD-03", "9", "Task 9.3 parent box"),
    (2870, "Latency targets defined and met", "OD-03", "9", "9.3 verification line"),
    (2953, "Performance baselines recorded and met", "OD-03", "9", "Stage 9 completion-gate line"),
    (3115, "**10.8 — Load and capacity planning**", "OD-04", "10", "Task 10.8 parent box"),
    (3126, "Document the onboarding limit", "OD-04", "10", "10.8 implementation item"),
    (3158, "Capacity limit known and documented", "OD-04", "10", "Stage 10 completion-gate line"),
    (3398, "Record accepted known issues", "OD-06", "12", "12.3 implementation item"),
    (3399, "Obtain and record written sign-off", "OD-21", "12", "12.3 implementation item (sign-off)"),
    (3402, "Written sign-off recorded in the repository", "OD-21", "12", "12.3 verification line (sign-off)"),
    (3487, "**Owner — telling intentional deletion apart from data loss at startup**", "OD-05", "12", "Stage 12 remediation owner box"),
    (3509, "**Owner — Stage 12.1 final decision package**", "OD-07", "12", "Stage 12.1 record owner box (roll-up)"),
    (3531, "**Owner — handling of the intermittent live-model cast test**", "ALREADY DECIDED", "12", "Stage 12.3 record owner box (CLOSED 2026-10-06)"),
    (None, "**Owner — New finding (2026-10-06): Writing Suggestions has no way in from the studio**", "OD-09", "12", "Stage 12.3 record owner box (new 2026-10-06)"),
    (3543, "Product owner sign-off recorded", "OD-21", "12", "Stage 12 completion-gate line (sign-off)"),
    (3558, "AI quality improvement demonstrated by measurement against the Stage 5 baseline", "OD-08", "Final", "Final Project Completion line"),
]
CLOSED_BOXES = {"ALREADY DECIDED"}
BOX_STATE: dict[str, bool] = {}   # label -> open now (filled by the validator)

DECISION_IDS = [f"OD-{i:02d}" for i in range(1, 22)]
BOX_DECISIONS = [f"OD-{i:02d}" for i in range(1, 11)] + ["OD-21"]
SUPPORTING = [f"OD-{i:02d}" for i in range(11, 21)]
SIGNOFF = "OD-21"

P_ = "PENDING OWNER DECISION"
# Summary rows: id, topic, stage, gate, release-blocking, recommended option, status
SUMMARY = [
    ("OD-01", "Story Audit: accept 5.14's three partial items (MV-5.14-D) and the Story Audit issue group (G5)", "5", "Gate 3b (A4); Gate 4 (G5)", "YES", "B \u2014 Accept with follow-up (each item); G5 after your reading", P_),
    ("OD-02", "Accept the 30 deferred (post-launch, Medium) issues", "9", "Stage 9 (9.2); Final checklist", "NO", "A \u2014 Accept all 30 as deferred", P_),
    ("OD-03", "Latency targets: how to treat the 50 % Tier-2 search tail (linked to OD-04)", "9", "Stage 9 gate", "NO", "A \u2014 Met within the supported envelope; tail recorded as a limitation", P_),
    ("OD-04", "Onboarding limit per pod (MV-10.8) (linked to OD-03)", "10", "Stage 10 gate", "NO", "A \u2014 Accept 60 active / ~150\u2013200 registered, under 10 % Tier-2", P_),
    ("OD-05", "Telling intentional deletion apart from data loss at startup", "12", "Operations (no numbered gate)", "NO", "B \u2014 Operator \u2018.disposable\u2019 marker per backup set", P_),
    ("OD-06", "Record accepted known issues (final list)", "12", "Gate 9 (task 12.3)", "YES", "B \u2014 You confirm the final list before the box is ticked", P_),
    ("OD-07", "Stage 12.1 final decision package \u2014 roll-up box", "12", "Gates 3b, 4, 6, 9 (through its contents)", "YES", "A \u2014 Close automatically when every listed item is recorded", P_),
    ("OD-08", "Is \u2018AI quality improvement demonstrated by measurement\u2019 satisfied?", "Final", "Final Project Completion (depends on Gate 3b)", "NO", "B \u2014 Wait for Gate 3b re-validation", P_),
    ("OD-09", "Writing Suggestions has no way in from the studio: restore, retire or defer", "12", "Gate 4 (G6); Gate 3b (5.13 review)", "YES", "A \u2014 Restore as a studio tool", P_),
    ("OD-10", "Approve the AI-quality regression alarm rule (task 6.5 \u2018agreed threshold\u2019)", "6", "Stage 6 (6.5)", "NO", "A \u2014 Approve as is", P_),
    ("OD-11", "Rule: G3 rewrite-quality closure (HR-01\u2013HR-05, HR-08)", "Supporting", "Gate 3b; Gate 4 (G3)", "YES", "A \u2014 Per-issue rule", P_),
    ("OD-12", "Rule: G1 Light re-validation tie at exactly 6/12 (HR-06)", "Supporting", "Gate 3b; Gate 4 (G1)", "YES", "A \u2014 6/12 counts as FAIL", P_),
    ("OD-13", "Rule: Light warning/retry level from the labels (HR-07, A15)", "Supporting", "Gate 3b; Gate 4 (G1, supporting)", "YES", "A \u2014 Derive from your labels; you approve the number", P_),
    ("OD-14", "Rule: children's meaning tolerance (HR-08, A3)", "Supporting", "Gate 3b; Gate 4 (G3 audience)", "YES", "A \u2014 Strict: every rewrite \u2018Kept\u2019", P_),
    ("OD-15", "Rule: G5 Story Audit per-issue closure (HR-09)", "Supporting", "Gate 3b; Gate 4 (G5)", "YES", "A \u2014 None/Minor close; Major/Blocking open", P_),
    ("OD-16", "Rule: G6 Suggestions per-issue closure (HR-11)", "Supporting", "Gate 4 (G6)", "YES", "A \u2014 None/Minor close; Major/Blocking open", P_),
    ("OD-17", "Rule: G7 Plot Assistant \u2018Partly correct\u2019 and per-issue closure (HR-12)", "Supporting", "Gate 4 (G7)", "YES", "A \u2014 Incomplete-but-not-wrong passes; per-issue A", P_),
    ("OD-18", "Rule: G8 Studio UI per-issue closure (HR-13\u2013HR-15)", "Supporting", "Gate 4 (G8)", "YES", "A \u2014 None/Minor close; Major/Blocking open", P_),
    ("OD-19", "Rules: A6 thresholds \u2014 5.15 \u2018Partly\u2019 (HR-17), 7.12 style match (HR-18), 5.10 identity (HR-19)", "Supporting", "Gate 3b (A6)", "YES", "A for each", P_),
    ("OD-20", "Rule: 11.7 \u2018Possible imitation\u2019 handling (HR-20)", "Supporting", "Gate 9 prerequisite (11.7)", "YES", "A \u2014 Send to legal counsel with the legal review", P_),
    ("OD-21", "FINAL RELEASE SIGN-OFF (written approval of v3.3.0)", "12", "Gate 9", "YES", "No recommendation \u2014 owner's own approval; blocked", "BLOCKED \u2014 PREREQUISITES NOT COMPLETE"),
]

RELEASE_BLOCKING = {r[0]: r[4] for r in SUMMARY}

GATE_DIR = REPO / "docs/testing/stage-12/stage-12.3/ai-quality-gate"


def _gate_result_lines() -> list[str]:
    """Quote the live-proof result lines if the files exist; never invent them."""
    import json
    names = [("baseline.json", "Baseline (unchanged code)"), ("rerun-unchanged.json", "Re-run, unchanged code"),
             ("injected-degraded-no-change.json",
              "Injected Stage 12.1 'tightening' sentence (this edit does not change the model's behaviour on the "
              "current code, so no alarm is the correct outcome)"),
             ("injected-renamed-assessor-key.json",
              "Injected prompt/parser drift in the no-change assessor (behaviour-changing regression; the alarm "
              "must fire)")]
    if not any((GATE_DIR / n).exists() for n, _ in names):
        return ["Results: see docs/testing/stage-12/stage-12.3/ai-quality-gate/ (baseline.json, rerun-unchanged.json, "
                "injected-degraded-no-change.json). The live proof was still running when this workbook was built "
                f"({TODAY}); no result is quoted or assumed here."]
    out = []
    for n, title in names:
        f = GATE_DIR / n
        if not f.exists():
            out.append(f"{title}: not yet recorded (ai-quality-gate/{n}).")
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            out.append(f"{title}: ai-quality-gate/{n} could not be read ({type(exc).__name__}).")
            continue
        if "verdict" in data:
            v = data["verdict"]
            flagged = [r["invariant"] + f" {r['baseline']}\u2192{r['observed']}" for r in v.get("rows", []) if r.get("ALARM")]
            out.append(f"{title} (ai-quality-gate/{n}): " + ("REGRESSION ALARM \u2014 " + "; ".join(flagged)
                                                             if v.get("alarm") else "no regression detected") + ".")
        else:
            inv = data.get("invariants", {})
            parts = [f"{k} {x.get('passes')}/{x.get('trials')}" for k, x in inv.items()]
            out.append(f"{title} (ai-quality-gate/{n}): " + "; ".join(parts) + ".")
    return out


GATE_RESULT_LINES = _gate_result_lines()

# The 30 post-launch issues (docs/issues-and-bugs/triage-register.md, "(proposed)") with the Stage 9
# re-run status from docs/testing/stage-09-qa-rerun-results.md (2026-09-27) and later notes.
DEFERRED = [
    ("PA-M15", "Emotional arc not captured in summaries", "Plot Assistant", "4.5", "No evidence found (2026-09-27): existing emotional_tone field, no test"),
    ("PA-M16", "Relationship intelligence incomplete", "Plot Assistant", "4.5", "Live check needed; no AI relationship-extraction pipeline (4.9 Option B, 2026-10-03)"),
    ("SUG-M12", "Limited editorial depth", "Suggestions", "5.13", "Author judgement required (G6 usage review)"),
    ("SUG-M13", "Lack of recommendation prioritisation", "Suggestions", "5.13", "PASS — automated"),
    ("SUG-M14", "Missing contrarian analysis", "Suggestions", "5.13", "Mechanism tested; usefulness is author judgement"),
    ("SUG-M15", "Insufficient story-intelligence integration", "Suggestions", "5.13", "No evidence found (same wiring gap as SUG-H9)"),
    ("SUG-M16", "Observation vs recommendation mismatch", "Suggestions", "5.13", "PASS — automated (structure); fit is judgement"),
    ("CAST-M11", "Minor character promotion", "Cast", "4.9", "PASS — automated (single-case fixture)"),
    ("CAST-M12", "Mention-to-character linking failure", "Cast", "4.9", "PASS — automated (unit level)"),
    ("CAST-M13", "Character memory fragmentation", "Cast", "4.8", "PASS — automated (author-initiated merge)"),
    ("CAST-M14", "Story-wide character consolidation failure", "Cast", "4.8", "PASS — automated (as CAST-M13)"),
    ("AUDIT-M11", "Relationship arc analysis missing", "Story Audit", "5.14", "Relationships section built; MV-5.14-C passed live 2026-10-03; acceptance is OD-01"),
    ("AUDIT-M12", "Theme analysis missing", "Story Audit", "5.14", "Theme analysis built (5.14 ticked); shown in the report since Stage 12.1"),
    ("AUDIT-M13", "Generic improvement recommendations", "Story Audit", "5.14", "Author judgement required"),
    ("AUDIT-M14", "Limited developmental editing insights", "Story Audit", "5.14", "Author judgement required"),
    ("AUDIT-M15", "Narrative intelligence depth limited", "Story Audit", "5.14", "Author judgement required"),
    ("ANLY-M1", "Analytics lack transparency", "Analytics", "5.15", "Author judgement required (5.15 interpretability review)"),
    ("ANLY-M2", "Readability score lacks explanation", "Analytics", "5.15", "PASS — automated"),
    ("ANLY-M3", "Dialogue ratio lacks genre context", "Analytics", "5.15", "PASS — automated"),
    ("ANLY-M4", "No genre-aware analytics", "Analytics", "5.15", "PASS — automated"),
    ("ANLY-M5", "Limited actionability", "Analytics", "5.15", "Author judgement required"),
    ("ANLY-M6", "Missing story-intelligence integration", "Analytics", "5.15", "No evidence found (only the ‘without’ case tested)"),
    ("SEARCH-10", "Search engine consistency problems", "Search", "4.14", "PASS — automated"),
    ("SEARCH-11", "Regex/tokenisation handling issue", "Search", "4.14", "PASS — automated"),
    ("SEARCH-12", "Overlapping chunk results", "Search", "4.13", "PASS — automated"),
    ("SEARCH-13", "Search result diversity reduction", "Search", "4.13", "PASS — automated"),
    ("SEARCH-14", "Result ranking optimisation needed", "Search", "4.14", "PASS — automated"),
    ("UI-M16", "Information architecture needs redesign", "Editor UI", "8.8", "PASS — automated (‘reads as a studio’ part is MV-8.5/8.7)"),
    ("UI-M17", "Layout feels like a dashboard, not a studio", "Editor UI", "8.3 / 8.8", "Author judgement required (G8 usage review)"),
    ("UI-M18", "Future feature expansion will increase friction", "Editor UI", "8.7", "PASS — automated"),
]

# --------------------------------------------------------------------------------------------
# Document helpers
# --------------------------------------------------------------------------------------------
doc = Document()


def _set_cell_shading(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _add_runs(p, text: str, size: float | None = None, color: RGBColor | None = None):
    """Add text with **bold** markup."""
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2])
            r.bold = True
        else:
            r = p.add_run(part)
        if size:
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
    return p


def para(text: str = "", style: str | None = None, size: float | None = None, align=None,
         color: RGBColor | None = None, space_after: float | None = None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _add_runs(p, text, size, color)
    if align is not None:
        p.alignment = align
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def bullet(text: str, level: int = 0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    _add_runs(p, text)
    return p


def h(text: str, level: int):
    return doc.add_heading(text, level=level)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def table(header: list[str], rows: list[list[str]], widths_cm: list[float] | None = None,
          font_size: float = 9, header_fill: str = "1F3864"):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, head in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(head)
        r.bold = True
        r.font.size = Pt(font_size)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _set_cell_shading(c, header_fill)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            _add_runs(cells[i].paragraphs[0], str(val), size=font_size)
    if widths_cm:
        for row in t.rows:
            for i, w in enumerate(widths_cm):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def kv_table(rows: list[tuple[str, str]]):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in rows:
        cells = t.add_row().cells
        cells[0].text = ""
        r = cells[0].paragraphs[0].add_run(k)
        r.bold = True
        r.font.size = Pt(9.5)
        _set_cell_shading(cells[0], "D9E2F3")
        cells[1].text = ""
        _add_runs(cells[1].paragraphs[0], v, size=9.5)
    for row in t.rows:
        row.cells[0].width = Cm(4.2)
        row.cells[1].width = Cm(12.3)
    doc.add_paragraph()
    return t


def add_field(paragraph, instr: str, placeholder: str = ""):
    """Insert a complex field (TOC, PAGE, ...)."""
    r = paragraph.add_run()
    f1 = OxmlElement("w:fldChar")
    f1.set(qn("w:fldCharType"), "begin")
    f1.set(qn("w:dirty"), "true")
    r._r.append(f1)
    r2 = paragraph.add_run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    r2._r.append(it)
    r3 = paragraph.add_run()
    f2 = OxmlElement("w:fldChar")
    f2.set(qn("w:fldCharType"), "separate")
    r3._r.append(f2)
    r4 = paragraph.add_run(placeholder)
    r5 = paragraph.add_run()
    f3 = OxmlElement("w:fldChar")
    f3.set(qn("w:fldCharType"), "end")
    r5._r.append(f3)
    return r4


def _box_re(state: str = "[ x]") -> "re.Pattern[str]":
    return re.compile(r"^\s*- \[" + state + r"\]")


WORK_LINES = (REPO / CHECKLIST).read_text(encoding="utf-8").splitlines()


def current_line(label: str) -> list[int]:
    """Working-tree line(s) of the checkbox carrying this exact label (located by text, not number)."""
    return [i + 1 for i, l in enumerate(WORK_LINES) if label in l and _box_re().match(l)]


def line_ref(head, label: str) -> str:
    cur = current_line(label)
    today = f"L{cur[0]}" if len(cur) == 1 else "not found"
    return (f"L{head} at HEAD / {today} today" if head else f"new after HEAD / {today} today")


def box_quote(label_start: str) -> str:
    for _ln, label, *_ in BOXES:
        if label.replace("**", "").startswith(label_start):
            return label.replace("**", "")
    raise KeyError(label_start)


def boxes_for(od: str) -> list[tuple[str, str, str]]:
    return [(line_ref(ln, label), label.replace("**", ""), role) for ln, label, o, _s, role in BOXES if o == od]


CURRENT_OD = [""]


def decision_meta(od: str, stage: str, d6: str, gate: str, when: str, extra: list[tuple[str, str]] | None = None):
    CURRENT_OD[0] = od
    bl = boxes_for(od)
    box_lines = ("\n".join(f"{ref} \u2014 \u201c{q}\u201d ({role})" for ref, q, role in bl) if bl else
                 "None \u2014 supporting decision (no checklist box of its own). It decides how human review results "
                 "close D-6 items.")
    rows = [
        ("Decision ID", od),
        ("Stage", stage),
        ("Checklist box(es) (line at HEAD " + HEAD + " / today, located by text; exact text)", box_lines),
        ("Related D-6 IDs", d6),
        ("Gate affected", gate),
        ("Release-blocking", RELEASE_BLOCKING[od]),
        ("When to answer", when),
    ]
    if extra:
        rows.extend(extra)
    kv_table(rows)


def options_table(options: list[tuple[str, str, str, str, str]]):
    table(["Option", "What it means", "Effect", "Risk", "Checklist consequence"],
          [list(o) for o in options], widths_cm=[1.6, 4.4, 3.6, 3.6, 3.6], font_size=8.5)


def recommendation(rec: str, why: str):
    p = para(f"**TECHNICAL RECOMMENDATION:** {rec}")
    p.paragraph_format.space_before = Pt(4)
    para(f"**WHY:** {why}")
    para("This is engineering advice only. It is not a decision and nothing has been chosen for you.",
         size=8.5, color=RGBColor(0x59, 0x59, 0x59))


# --------------------------------------------------------------------------------------------
# OWNER ANSWERS — recorded from the owner's written instruction of 2026-10-06 (chat). Transcribed, not inferred.
# Keys are the answer-line prefix after "OWNER ANSWER — "; values are the chosen option's leading text.
# OD-21 has NO chosen box: the owner's current position is recorded as text only.
# --------------------------------------------------------------------------------------------
BOX_X = "☒"  # ☒ — used only for an option the owner chose
RECORDED_LINE = ("Recorded from the owner's written instruction of 2026-10-06 (chat), transcribed by the "
                 "implementation agent.")
ANSWERS = {
    "OD-01 (1)": "B", "OD-01 (2)": "B", "OD-01 (3)": "B", "OD-01 (4)": "Issue-by-issue",
    "OD-02": "A", "OD-03": "A", "OD-04": "A", "OD-05": "B", "OD-06": "B", "OD-07": "A", "OD-08": "B",
    "OD-09": "A", "OD-10": "A", "OD-11": "A", "OD-12": "A", "OD-13": "A", "OD-14": "A", "OD-15": "A",
    "OD-16": "A", "OD-17 (1)": "A", "OD-17 (2)": "A", "OD-18": "A",
    "OD-19 (1)": "A", "OD-19 (2)": "A", "OD-19 (3)": "A", "OD-20": "A",
}
OWNER_NOTES = {
    "OD-01": "B — accept with follow-up for the three partial MV-5.14-D items (timeline, narrative, relationship arcs). "
             "NOT unconditional acceptance of every Story Audit defect. G5 is decided issue by issue from HR-09 (rule "
             "OD-15); any Major/Blocking found by HR-09 remains open unless separately accepted. The partial items are "
             "recorded as accepted known limitations / follow-ups.",
    "OD-02": "A — accept all 30 as deferred post-launch Medium issues; they do not block v3.3.0; preserve them in the "
             "post-launch backlog; never show them as fixed.",
    "OD-03": "A — accept as meeting the supported production envelope; the ~50 % Tier-2 search tail is an accepted "
             "known limitation within the measured envelope; record it in the known limitations; never claim it is absent.",
    "OD-04": "A — about 60 active authors per pod, about 150–200 registered, under 10 % simultaneous Tier-2. This is "
             "the initial supported envelope, not an unlimited claim; scaling needs capacity work and re-validation.",
    "OD-05": "B — operator ‘.disposable’ marker per backup set; implement and document exactly as designed; do not "
             "weaken the startup data-loss protection.",
    "OD-06": "B — the final list needs owner confirmation before its box is ticked. Engineering is authorised to build "
             "and reconcile the complete proposed list automatically from accepted decisions, residual risks, "
             "limitations, deferred Medium issues and the current human review. The owner will not reconfirm "
             "already-decided items individually. The box stays open until the reconciled list exists.",
    "OD-07": "A — closes automatically when every constituent item is properly recorded; no ceremonial confirmation.",
    "OD-08": "B — not closed from historical measurements; closes only after current human re-validation and Gate 3b "
             "evidence support it; stays open if Gate 3b fails.",
    "OD-09": "A — restore Writing Suggestions as an accessible Studio tool with a discoverable route; verify it; then run "
             "HR-11 against the accessible feature.",
    "OD-10": "A — approve the implemented 6.5 alarm rule as technically defined and verified; record it as the agreed "
             "threshold; preserve the variance-aware method and the deliberate-regression proof.",
    "OD-11": "A — per-issue closure. Critical: HR-05 Accept AND no Blocking tagged answer in HR-01–HR-04/HR-08. High: "
             "transform summary Accept AND no Blocking tagged answer.",
    "OD-12": "A — exactly 6/12 = FAIL.",
    "OD-13": "A — derive the threshold from the HR-07 labels; report and record the derived value; no arbitrary number.",
    "OD-14": "A — strict: every item Kept. Vocabulary simplification is allowed; changes to facts, consequences, intent, "
             "point of view or meaning fail.",
    "OD-15": "A — None/Minor close (Minor: record the observation); Major/Blocking stay open.",
    "OD-16": "A — same rule as OD-15; Suggestions must actually be accessible from the Studio (OD-09).",
    "OD-17": "A — Correct passes; Partly correct passes only if incomplete but accurate; partly correct with a factual "
             "contradiction, Incorrect or Invented fail; decided per issue; fabricated information is never "
             "“partly correct”.",
    "OD-18": "A — None/Minor close; Major/Blocking stay open.",
    "OD-19": "A for all three. (1) Partly allowed with a documented note: PASS when overall YES, no metric No, and each "
             "Partly explained. (2) “closely” better than Off in at least 2 of 3 chapters. (3) The human summary "
             "governs and every 1–2 rating is surfaced; a Strong rewrite is not bad merely because it changes more.",
    "OD-20": "A — every Possible imitation goes to legal counsel with the required legal review. No imitation passes; "
             "Possible imitation is pending legal (not a pass); Clear imitation FAILS with remediation. Option C is not used.",
}
# Implementation status written by the agent after the owner-authorised agent review (2026-10-06).
# Rendered under each decision as a SEPARATE, labelled paragraph — never as the owner's words.
AGENT_STATUS_LABEL = "IMPLEMENTATION STATUS (AI agent, 2026-10-06 — not the owner's words)"
AGENT_STATUS = {
    "OD-05": "Implemented: operator '.disposable' marker per backup set (scripts/backup_evidence.py, startup_backup.sh, "
             "backup_retention.py; tests scripts/tests/test_disposable_marker.py). The empty-database guard is unchanged.",
    "OD-09": "Implemented and verified: Write → AI assistant → Generate → Suggestions (tests/studio/suggestions.spec.ts). "
             "HR-11 then ran on it: FAIL (box 5.13); two live defects fixed during the review (mid-word excerpt; false "
             "'repeated verbatim' claims).",
    "OD-11": "Applied in HR-01 – HR-05, HR-08, HR-19: every G3 transform failed its absolute review; no Critical or High G3 "
             "issue closes under this rule.",
    "OD-12": "Applied in HR-06: FAIL (re-run after the OD-13 fix also FAIL).",
    "OD-13": "Derived value: tone/style Light new-word-share limit 0.24 (Youden's J on the HR-07 labels; setting "
             "LIGHT_NEW_SHARE_MAX_TONE_STYLE, default 0.24); audience (age-adapt) keeps 0.45. Live re-measure: tone Light "
             "median new share 0.358 → 0.269. Evidence backend/tests/fixtures/strength_t2b_after_v4_light_repair_od13.json.",
    "OD-14": "Applied in HR-08: FAIL.",
    "OD-15": "Applied in HR-09: AUDIT-C2, C4, H9 close; C1, C3, C5, H6, H7, H8, H10 stay open.",
    "OD-16": "Applied in HR-11: SUG-C1, H4, H6 close; C2, H3, H5, H7, H8, H10, H11 stay open.",
    "OD-17": "Applied in HR-12: PA-C1, PA-H13 close; PA-C9, H10, H11 stay open.",
    "OD-18": "Applied in HR-13 – HR-15: UI-C2, H9, H10, H14 close; UI-C1, C6, H11, H13 stay open (HR-14 FAIL; HR-15 incomplete).",
    "OD-19": "Applied: HR-17 FAIL (one metric 'No'), HR-18 FAIL ('closely' won 1 of 3 real rewrites), HR-19 FAIL.",
    "OD-20": "Applied in HR-20: outputs O10 – O12 'Possible imitation' → pending legal review (INCOMPLETE).",
}
SUMMARY_ANSWERS = {
    "OD-01": "B (each item); G5 issue-by-issue per HR-09 / OD-15", "OD-02": "A", "OD-03": "A", "OD-04": "A",
    "OD-05": "B", "OD-06": "B", "OD-07": "A", "OD-08": "B", "OD-09": "A", "OD-10": "A", "OD-11": "A", "OD-12": "A",
    "OD-13": "A", "OD-14": "A", "OD-15": "A", "OD-16": "A", "OD-17": "A (both)", "OD-18": "A", "OD-19": "A (all three)",
    "OD-20": "A", "OD-21": "NOT APPROVED YET — PREREQUISITES NOT COMPLETE (not a rejection)",
}
OD21_POSITION = ("NOT APPROVED YET — PREREQUISITES NOT COMPLETE. (Explicitly not a rejection of NarratIQ; "
                 "no approval box is ticked and the signature, date and approval fields stay blank.)")

ANSWER_LINES: list[str] = []
CHOSEN: dict[str, str] = {}


def _answer_key(rest: str):
    keys = [k for k in ANSWERS if rest.startswith(k + " ") or rest == k or rest.startswith(k + ":")]
    return max(keys, key=len) if keys else None


def owner_answer(choices: list[str], label: str = "OWNER ANSWER"):
    if label == "OWNER ANSWER":
        label = f"OWNER ANSWER — {CURRENT_OD[0]}"
    elif not label.startswith("OWNER ANSWER"):
        label = f"OWNER ANSWER — {label}"
    ANSWER_LINES.append(label)
    rest = label.split("—", 1)[1].strip() if "—" in label else ""
    key = _answer_key(rest)
    chosen = [c for c in choices if key and c.startswith(ANSWERS[key])]
    if key and len(chosen) != 1:
        raise SystemExit(f"answer {key}={ANSWERS[key]!r} does not match exactly one option of {choices}")
    if key:
        CHOSEN[label] = chosen[0]
    p = doc.add_paragraph()
    r = p.add_run(f"{label}: ")
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    for c in choices:
        mark = BOX_X if (key and c == chosen[0]) else BOX
        rr = p.add_run(f"   {mark} {c}")
        rr.font.size = Pt(11)
        if mark == BOX_X:
            rr.bold = True
    return p


def owner_notes(label: str = "OWNER NOTES (optional)"):
    text = OWNER_NOTES.get(CURRENT_OD[0])
    p = doc.add_paragraph()
    r = p.add_run(f"{label}: ")
    r.bold = True
    if text:
        p.add_run(text)
        p2 = doc.add_paragraph()
        r2 = p2.add_run(RECORDED_LINE)
        r2.italic = True
        r2.font.size = Pt(9)
        doc.add_paragraph("Date (UTC): 2026-10-06")
        status = AGENT_STATUS.get(CURRENT_OD[0])
        if status:
            p3 = doc.add_paragraph()
            r3 = p3.add_run(f"{AGENT_STATUS_LABEL}: ")
            r3.bold = True
            r3.font.size = Pt(9)
            r4 = p3.add_run(status)
            r4.font.size = Pt(9)
    else:
        p.add_run("_" * 70)
        doc.add_paragraph("_" * 95)
        doc.add_paragraph("Date (UTC): ____________________")


def blank_line(label: str):
    p = doc.add_paragraph()
    r = p.add_run(f"{label}: ")
    r.bold = True
    p.add_run("_" * 70)


# --------------------------------------------------------------------------------------------
# Page setup, styles, header and footer
# --------------------------------------------------------------------------------------------
sec = doc.sections[0]
sec.page_height = Cm(29.7)
sec.page_width = Cm(21.0)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = Cm(2.2)
sec.bottom_margin = Cm(2.0)
sec.different_first_page_header_footer = True

normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10.5)
for lvl, size, colr in ((1, 16, "1F3864"), (2, 13, "2E74B5"), (3, 11, "1F3864")):
    st = doc.styles[f"Heading {lvl}"]
    st.font.size = Pt(size)
    st.font.color.rgb = RGBColor.from_string(colr)

hp = sec.header.paragraphs[0]
hp.text = HEADER_TEXT
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
for r in hp.runs:
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)

fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run("Owner decision workbook — owner answers recorded 2026-10-06; OD-21 not signed — Page ")
fr.font.size = Pt(8.5)
add_field(fp, "PAGE", "1")

# --------------------------------------------------------------------------------------------
# Title page
# --------------------------------------------------------------------------------------------
for _ in range(5):
    doc.add_paragraph()
para("NarratIQ AI", size=14, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x59, 0x59, 0x59))
para("Owner Decision Package", size=30, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x1F, 0x38, 0x64))
para("v3.3.0 Release Candidate — decision workbook for the product owner", size=14,
     align=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph()
para(f"Prepared {TODAY} from repository HEAD {HEAD}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
para("Prepared for: the product owner     Prepared by: engineering (advice only)", size=11,
     align=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_paragraph()
para("**Status: OWNER ANSWERS RECORDED (2026-10-06) for OD-01 – OD-20.** The chosen options (\u2612) and the owner's "
     "conditions were transcribed from the owner's written instruction of 2026-10-06; engineering did not choose. "
     "**OD-21 (release sign-off) is NOT signed:** owner's current position \u201cNOT APPROVED YET \u2014 PREREQUISITES "
     "NOT COMPLETE\u201d.",
     size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
para("**Release status: v3.3.0 is NOT approved.** The final sign-off section is blocked until its "
     "prerequisites pass.", size=11, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0xC0, 0x00, 0x00))
doc.add_paragraph()
para("Companion document: NarratIQ_Human_Review_Package.docx (the reading and labelling reviews, including the "
     "Story Audit review). Some decisions here should be answered after those reviews; each says so.",
     size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x59, 0x59, 0x59))
page_break()

# --------------------------------------------------------------------------------------------
# Purpose and how to use
# --------------------------------------------------------------------------------------------
h("Purpose of this workbook", 1)
para("NarratIQ's master implementation checklist still has open boxes that only you, as product owner, can "
     "close. This workbook gathers them in one place, explains each in plain English, and gives you a place to "
     "write your answer. When you return it, engineering records your answers exactly as given and ticks only "
     "the boxes your answers allow.")
h("How to use it", 2)
bullet("Read the summary table first. It lists every decision, whether it blocks the release, and what "
       "engineering recommends.")
bullet("For each decision, tick **one** ☐ box next to “OWNER ANSWER”. Add notes if you want a condition "
       "or a follow-up recorded.")
bullet("Some decisions say **“answer after …”**. They depend on a human review (for example the Story Audit "
       "reading in the Human Review Package). You can still read them now.")
bullet("Do **not** complete the final section, “FINAL RELEASE SIGN-OFF — DO NOT COMPLETE YET”. It is blocked "
       "until the listed prerequisites pass.")
bullet("Nothing in this workbook asks you to re-decide anything you have already decided (see “Already decided "
       "— do not re-decide”).")
h("Ground rules engineering followed", 2)
bullet("No answer was pre-filled, guessed or inferred. The answers now shown were recorded from the owner's written "
       "instruction of 2026-10-06. “TECHNICAL RECOMMENDATION” is advice, not a decision.")
bullet("Each decision quotes the exact checklist box text and its line number at repository HEAD " + HEAD + ".")
bullet("No passwords, keys or tokens appear in this workbook.")
bullet("“Release-blocking” follows the sign-off record (docs/releases/v3.3.0-sign-off.md §9) and the "
       "production gates.")

h("Table of contents", 1)
para("Right-click the table below and choose “Update Field” (or press F9) in Microsoft Word to fill in or "
     "refresh the table of contents and page numbers.", size=9, color=RGBColor(0x59, 0x59, 0x59))
add_field(doc.add_paragraph(), 'TOC \\o "1-3" \\h \\z \\u',
          "[Table of contents — update this field in Word]")
page_break()

# --------------------------------------------------------------------------------------------
# Summary table
# --------------------------------------------------------------------------------------------
h("Decision summary", 1)
para("Owner Answer and Status record the owner's written instruction of 2026-10-06 (transcribed by the implementation "
     "agent). OD-21 remains BLOCKED and unsigned.")
table(["Decision ID", "Topic", "Stage", "Gate", "Release Blocking", "Recommended Option", "Owner Answer", "Status"],
      [[r[0], r[1], r[2], r[3], r[4], r[5], SUMMARY_ANSWERS[r[0]], ("ANSWERED" if r[0] != SIGNOFF else r[6])] for r in SUMMARY],
      widths_cm=[1.5, 4.0, 1.1, 2.4, 1.4, 3.0, 1.6, 2.0], font_size=8)
para("**Linked decisions:** OD-03 (latency targets) and OD-04 (onboarding limit) rest on the same capacity "
     "measurement and should be answered together. OD-07 is a roll-up that closes when the decisions and reviews "
     "it lists are complete. OD-09 (Suggestions has no way in from the studio) decides whether OD-16 (the G6 review "
     "rule) applies to a live feature. OD-11 to OD-20 are **supporting rules** with no checklist box of their own: "
     "they set the pass bar for the human reviews and are best answered **before** those reviews. OD-21 is the release "
     "sign-off and is blocked.")
page_break()

# --------------------------------------------------------------------------------------------
# Current release context
# --------------------------------------------------------------------------------------------
h("Current release context", 1)
para("v3.3.0 is a **release candidate, not a release**. The application still reports version 3.0.0, and the "
     "sign-off record (docs/releases/v3.3.0-sign-off.md) is **unsigned**. The release commit has not been made and "
     "the repository has no tags.")
h("Production gates (from the sign-off record)", 2)
table(["Gate", "Status (2026-10-05)"], [
    ["1 Environment stable", "PASSED"],
    ["2 Core workflows functional", "PASSED"],
    ["3a Retrieval correct", "PASSED (on owner decision B2)"],
    ["3b AI quality acceptable", "**OPEN** — A1 blind review passed; A2 Light vs Strong failed, fixed, re-validation pending; A3–A6 not done"],
    ["4 No critical defects", "**OPEN** — 75 release-blocking issues undecided (20 Critical / 55 High)"],
    ["5 Security checks passed", "PASSED WITH ACCEPTED RISKS (S1–S6 decided)"],
    ["6 End-to-end tests passed", "**OPEN** — W-1 regression on the exact release commit not yet possible; real-author UAT not done"],
    ["7 Backup and recovery verified", "PASSED (off-pod copy: W-3)"],
    ["8 Deployment and rollback tested", "PASSED WITH WAIVER (W-2; presence-label loss accepted)"],
    ["9 Release approval", "**NOT GIVEN**"],
], widths_cm=[5.0, 11.5])
h("Standing release conditions (not decisions in this workbook)", 2)
para("These are already set. They are listed so the context is complete; they are **not** questions here.")
bullet("**W-3 — off-pod backup (not waived):** no real author manuscripts or data may be accepted or stored in "
       "production until an approved off-pod backup destination exists **and** one restore from it has been "
       "verified. No provider is configured yet. This is an external-infrastructure item.")
bullet("**W-5 — SECRET_KEY copy (open):** stays open until you personally confirm the production signing key "
       "has been copied to a separate secret store. This is an owner confirmation, not a decision; never paste the "
       "key into any document or chat.")
bullet("**W-1 — CI waived with condition:** the full regression must be run and recorded against the exact "
       "release commit (needs your commit).")
h("Already decided — do not re-decide", 2)
para("Recorded in docs/testing/stage-12/stage-12.1/owner-decisions.md and the sign-off record §3–§4. This "
     "workbook does not ask about them again:")
table(["Item", "Your recorded decision"], [
    ["B1 AWT-G run-to-run consistency", "ACCEPT (criterion recorded as NOT MET)"],
    ["B2 CAST-H6 role classification", "ACCEPT"],
    ["B3 PA-C6 / B4 PA-H12 retrieval", "ACCEPT + post-release follow-up"],
    ["S1–S6 security residuals", "S1 accepted residual risk; S2 confirm (127.0.0.1 only); S3, S6 accept; S4, S5 accept + follow-up"],
    ["Presence labels lost on rollback past 0027", "ACCEPT (rollback not completely lossless)"],
    ["W-1 / W-2 / W-4 waivers", "W-1 waive with condition; W-2 waive; W-4 waive + daily manual check"],
    ["CAST-H10 presence-label variability", "ACCEPTED as model variability (2026-10-03)"],
    ["Cast-test technical treatment", "APPROVED 2026-10-06 (option 3) and implemented; L3531 CLOSED — see next section"],
    ["A1 blind review and Gate 3b", "A1 recorded as PASS; you directed that A1 alone does not close Gate 3b's G3 group"],
    ["4.9 relationship extraction; Story Bible example leak; translation", "Option B (not applicable); fix now (done); translation stays open and release-blocking"],
], widths_cm=[6.0, 10.5])

h("Already decided — no answer needed: the intermittent live-model cast test (L3531, CLOSED)", 2)
para("Checklist box (L3531): “" + box_quote("Owner — handling of the intermittent") + "”.")
para("This box was counted among the **20** owner-decision boxes in the previous reconciliation. **It is now closed** "
     "(ticked in the checklist on 2026-10-06 as decided and implemented): on **2026-10-06** you approved option 3 "
     "— a hard, deterministic identity test; a separate, non-blocking measurement of presence-label variability; "
     "and a deterministic stub test that reproduces the known failure shape so a real regression would still be "
     "caught. The underlying variability (CAST-H10, the model sometimes labelling the living antagonist "
     "“historical”) was already accepted on 2026-10-03 as model variability (owner-decisions.md; "
     "gate4-section3-review.md).")
para("**No answer is needed.** Nothing about CAST-H10 remains undecided, so no CAST-H10 question is asked.")
para("**Open owner-decision boxes in this workbook: 21.** That is the 19 that remained after L3531 closed, plus two "
     "added on 2026-10-06: the new Stage 12.3 box “Writing Suggestions has no way in from the studio” "
     "(OD-09) and task 6.5 “Alert on regression beyond an agreed threshold” (OD-10), which moved from "
     "technical to owner because its threshold must be agreed by you.")
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 1 — Story Audit
# --------------------------------------------------------------------------------------------
h("Decision group 1 — Story Audit (Stage 5)", 1)
h("OD-01 — Story Audit: accept 5.14's three partial items (MV-5.14-D)", 2)
decision_meta(
    "OD-01", "Stage 5 (task 5.14 and the Stage 5 completion gate)",
    "AUDIT-C1–C5 (Critical), AUDIT-H6–H10 (High) — the G5 group; AUDIT-M11 (Medium, deferred list)",
    "Gate 3b (review A4, MV-5.14-D); Gate 4 (G5: 5 Critical + 5 High of the 75 undecided)",
    "**Answer after** your Story Audit reading in the Human Review Package (“Human Review Package — Story "
    "Audit review”). The evidence below is complete; only your reading is missing.",
    [("Grouped decision", "Five boxes, one decision. L2008, L2009 and L2014 are the three items; L1997 (the task) "
      "and L2067 (the gate line) close automatically when all three are accepted, because every other 5.14 item "
      "is already ticked.")])
h("What am I deciding?", 3)
para("Whether three improvements to the Story Audit (the Manuscript Report and Continuity Check) are good enough "
     "to count as done: (1) **timeline reasoning** — spotting events told in an impossible order; (2) **narrative "
     "reasoning** — spotting characters who vanish, threads that go nowhere and chapters with no purpose; "
     "(3) **relationship arcs** — a section showing how each pair of characters' relationship changes through "
     "the book. You decide each one separately, then whether the wider Story Audit issue group (G5) is accepted.")
h("Why is this decision required?", 3)
para("**Current behaviour.** All three are built and running. Timeline checks use dates, ages, weekdays, seasons "
     "and flashback cues (services/timeline_signals.py); narrative checks list vanished characters, dead-end threads "
     "and purposeless chapters in a “Things to check” section (services/narrative_signals.py); the "
     "“Relationships” section groups relationship changes by character pair in chapter order "
     "(services/relationship_arcs.py). Every continuity finding must cite real chapters or it is suppressed.")
para("**Technical evidence (live, 2026-10-03, docs/testing/stage-12/tranche3/):**")
bullet("**Timeline (MV-5.14-A, mv-5.14-a.json):** failed first — a clearly marked flashback was wrongly reported "
       "as an error 3/3 times. Fixed, then passed: planted date reversal reported 3/3; marked flashback 0/3.")
bullet("**Narrative (MV-5.14-B, mv-5.14-b.json, mv-5.14-b-section.png):** passed — the character who disappears "
       "after chapters 1–2 was listed with those chapters; every continuity finding cited real chapters.")
bullet("**Relationships (MV-5.14-C, mv-5.14-c.json, mv-5.14-c-section.png):** passed — current names, chapter chips, "
       "no raw ids. **Limitation:** the test story has only one pair with one change, so ordering across many "
       "pairs is barely exercised.")
bullet("**Observed weakness:** on the tiny test stories some continuity runs added weak findings (e.g. “Felix "
       "burned the rye” treated as contradicting his promise to help).")
bullet("Since Stage 12.1 the report also **shows** stakes, themes, plot weight and open threads (AUDIT-H8/H9/H10 "
       "display fix).")
para("**Alternatives.** Accept as built; accept and record a follow-up measurement; or reject an item and say what "
     "is missing (MV-5.14-D procedure, stage-05 manual verification guide).")
para("**Why engineering cannot choose.** Each item's technical criterion was met live. What remains is whether the "
     "findings are useful and trustworthy for a real author — a judgement the checklist assigns to you "
     "(MV-5.14-D: “The author decides whether the new dedicated mechanisms close the three items”).")
h("Available options (apply to each of the three items)", 3)
options_table([
    ("A", "Accept as built", "The item is ticked with the live evidence.",
     "Usefulness on full-length books is not measured; weak findings may waste an author's time (all are citation-checked).",
     "Item ticked; if all three are A or B, L1997 and L2067 close."),
    ("B", "Accept with a follow-up", "Ticked, and a post-release follow-up is recorded: measure finding relevance, and relationship arcs with several pairs, on a real-length manuscript.",
     "Same as A for this release; the gap is tracked.",
     "Item ticked + follow-up box added; L1997 and L2067 close if all three are A or B."),
    ("C", "Reject — require more work", "The item stays open; you say what is missing.",
     "Gate 3b and Gate 4 stay open on G5; release waits for the extra work.",
     "Item, L1997 and L2067 stay open; engineering scopes the work you name."),
])
recommendation("**B — Accept with follow-up** for all three items (timeline, narrative, relationships), "
               "confirmed by your Story Audit reading. For the G5 group: ACCEPT only if your reading found no false "
               "or uncited findings that would mislead an author; otherwise DEFER G5 to UAT.",
               "Each item met its own technical test live, and every finding is citation-checked, so nothing "
               "unsupported reaches the author. What is unproven is usefulness on real, long books — that is "
               "exactly what a follow-up measurement on a real-length manuscript would show, without holding the "
               "release on a judgement the tiny fixtures cannot settle.")
para("**Answer one line per item:**")
owner_answer(["A Accept", "B Accept + follow-up", "C Reject"], "OD-01 (1) Timeline reasoning — L2008, AUDIT-C4")
owner_answer(["A Accept", "B Accept + follow-up", "C Reject"], "OD-01 (2) Narrative reasoning — L2009, AUDIT-C5")
owner_answer(["A Accept", "B Accept + follow-up", "C Reject"], "OD-01 (3) Relationship arcs — L2014, AUDIT-M11")
owner_answer(["ACCEPT whole group", "DEFER to UAT", "Issue-by-issue per HR-09 / OD-15"], "OD-01 (4) G5 group AUDIT-C1–C5 / H6–H10 (D-6)")
para("The third G5 option was added on 2026-10-06 to record the owner's answer exactly as given.", size=8.5, color=RGBColor(0x59, 0x59, 0x59))
blank_line("If C (reject) or a follow-up: what is missing / which follow-up")
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 2 — Deferred issues
# --------------------------------------------------------------------------------------------
h("Decision group 2 — Deferred issues (Stage 9)", 1)
h("OD-02 — Accept the 30 deferred (post-launch) issues", 2)
decision_meta(
    "OD-02", "Stage 9 (task 9.2 verification)",
    "None of the D-6 release-blocking set. The 30 Medium issues listed in Appendix B (PA-M15/M16, SUG-M12–M16, "
    "CAST-M11–M14, AUDIT-M11–M15, ANLY-M1–M6, SEARCH-10–14, UI-M16–M18)",
    "Stage 9 task 9.2; Final checklist line “All 168 open issues closed, deferred with a recorded decision, or "
    "accepted per D-6”",
    "**Can be answered now.** If you plan to change OD-01 item (3) to Reject, keep AUDIT-M11 consistent with it.")
h("What am I deciding?", 3)
para("Whether you formally accept that 30 Medium-severity issues from the original QA reports are **deferred "
     "until after launch** rather than fixed before release.")
h("Why is this decision required?", 3)
para("**Current behaviour.** The issue register (docs/issues-and-bugs/triage-register.md) classifies issues by the "
     "D-6 severity rule you confirmed: Critical and High block release; Medium and Low are post-launch. 30 issues "
     "were classified post-launch, still marked “(proposed)”. The checklist requires each deferral to be "
     "explicitly accepted by you.")
para("**Technical evidence.** Stage 9 re-run (docs/testing/stage-09-qa-rerun-results.md, 2026-09-27): 16 of the 30 "
     "pass on automated tests; 8 need author judgement; 3 had no evidence; 3 depended on work then open (PA-M16 "
     "live check; AUDIT-M11 and AUDIT-M12 under task 5.14 — AUDIT-M11 is the relationships section in OD-01). "
     "Several have improved since. Appendix B lists every issue.")
para("**Alternatives.** Accept all; accept all except named ones; or leave open until UAT.")
para("**Why engineering cannot choose.** Deferring a known issue is a product decision about what ships; the "
     "register itself says no deferral is final without the product owner.")
h("Available options", 3)
options_table([
    ("A", "Accept all 30 as deferred (post-launch)", "The deferral is recorded for every issue.",
     "Some Medium usability/insight gaps ship as known; none is release-blocking under D-6.",
     "L2852 ticked; Final-checklist issue line moves closer to closure."),
    ("B", "Accept all except the issues you mark REJECT in Appendix B", "Rejected issues become work items or need a further decision.",
     "Adds pre-release work for any rejected issue.",
     "L2852 ticks only when every rejected issue is resolved or later accepted."),
    ("C", "Leave open (decide after UAT)", "Permitted: these issues are not release-blocking under D-6.",
     "9.2 and the final issue line stay open.", "L2852 stays open."),
])
recommendation("**A — Accept all 30 as deferred.**",
               "All 30 are Medium severity, so they are outside the release-blocking bar you set (D-6). More than half "
               "(16) already pass automated checks, and the rest are judgement items that UAT will inform better than a "
               "pre-release fix would.")
owner_answer(["A Accept all 30", "B Accept all except those marked in Appendix B", "C Leave open"])
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 3 — Capacity and performance (linked)
# --------------------------------------------------------------------------------------------
h("Decision group 3 — Capacity and performance (Stages 9 and 10, linked)", 1)
para("OD-03 and OD-04 rest on the same measurement (docs/operations/capacity-planning.md) and should be answered "
     "together. The latency box was explicitly “left open for the owner's capacity / onboarding decision "
     "(MV-10.8)”. In short: **one pod comfortably serves 60 active authors on free plans, and 60 when 10 % use "
     "the strict-consistency (Tier-2) option; at 50 % Tier-2 semantic search becomes slow at the tail.**")
table(["Plan mix (1 × A40 pod)", "Measured result", "Targets (approved S10-I: rewrite ≤ 8 s, Q&A ≤ 10 s, search ≤ 1 s p95)"], [
    ["Free / basic plans", "60 active authors: rewrite p95 3.3 s, Q&A 5.5 s, search 0.59 s, 0 errors", "All met"],
    ["10 % on Tier-2 strict consistency", "60 active authors: rewrite 6.1 s, Q&A 8.0 s, search 0.84 s, 0 errors (3-minute ramp level)", "All met"],
    ["50 % on Tier-2", "10 authors: search p95 3.6 s; 15 authors: search p95 1.2 s (median < 0.2 s); 20+: rewrite 17.9 s, Q&A 25.9 s, search 9.7 s", "**Not met** (search tail at 10–15; everything at 20+)"],
], widths_cm=[3.8, 8.0, 4.7])
para("The GPU is not the limit (the model server never queued). The limit is the CPU-based search/embedding "
     "model. Cheapest technical lever: run it on the GPU (BGE_DEVICE=cuda; ~2.3 GB of ~5.7 GB free VRAM) and "
     "re-measure — a production model-placement change, which is your decision.")

h("OD-03 — Latency targets: how to treat the 50 % Tier-2 search tail", 2)
decision_meta(
    "OD-03", "Stage 9 (task 9.3 and the Stage 9 completion gate)", "None (production gap PG-12)",
    "Stage 9 completion gate (“Performance baselines recorded and met”)",
    "**Can be answered now**, together with OD-04.",
    [("Grouped decision", "L2870 is the decision; L2855 (task 9.3) closes with it because every other 9.3 item is "
      "ticked; L2953 (gate line) follows it.")])
h("What am I deciding?", 3)
para("Whether the approved speed targets count as **met** for this release, given they are met for normal use but "
     "missed at the tail of search when half the active authors use Tier-2 strict consistency.")
h("Why is this decision required?", 3)
para("**Current behaviour.** Targets were approved on 2026-09-29 (S10-I, docs/testing/performance-baselines.md "
     "§6). They are met for single-author use (Stage 9), 60 free-plan authors (Stage 10) and 60 authors at "
     "10 % Tier-2 (2026-10-03). They are **not met strictly** at 50 % Tier-2 (table above).")
para("**Alternatives.** Count the targets as met within a defined operating envelope (enforced by the onboarding "
     "limit, OD-04); require a technical improvement first (GPU embeddings) and re-measure; or leave the box open.")
para("**Why engineering cannot choose.** “Met” here depends on which plan mix you intend to support, and the "
     "obvious fix changes production model placement — both product decisions.")
h("Available options", 3)
options_table([
    ("A", "Met within the supported envelope", "Targets recorded as met for single-author use, 60 free-plan authors and ≤ 10 % Tier-2; the 50 % Tier-2 search tail recorded as a known limitation, controlled by OD-04 and the scaling triggers.",
     "If Tier-2 use grows past 10 %, search can be slow (1.2–3.6 s p95) before the scaling trigger acts.",
     "L2870, L2855 and L2953 ticked with that condition."),
    ("B", "Improve first, then re-measure", "Move the embedding model to the GPU (BGE_DEVICE=cuda), re-run the Tier-2 ramp, tick only if every target is met.",
     "Pre-release change to production configuration; needs regression on the release commit; outcome not guaranteed.",
     "Boxes stay open until the re-measurement passes."),
    ("C", "Leave open", "Permitted: not listed as a release blocker (sign-off §9).",
     "Stage 9 gate stays open.", "L2870, L2855, L2953 stay open."),
])
recommendation("**A — Met within the supported envelope**, with GPU embeddings (option B's change) recorded as a "
               "post-release follow-up triggered by the scaling rules.",
               "Every target is met for the mixes the proposed onboarding limit allows, with zero errors in every "
               "run, and medians stay low even at 50 % Tier-2. Under W-3 no real author data can be stored yet, so "
               "there is no production load to protect today; the follow-up is cheap and aimed at the measured "
               "bottleneck.")
owner_answer(["A Met within envelope", "B Improve first", "C Leave open"])
owner_notes()

h("OD-04 — Onboarding limit per pod (MV-10.8)", 2)
decision_meta(
    "OD-04", "Stage 10 (task 10.8 and the Stage 10 completion gate)", "None (production gap PG-12)",
    "Stage 10 completion gate (“Capacity limit known and documented”)",
    "**Can be answered now**, together with OD-03. (The earlier package suggested UAT could inform it; option C allows that.)",
    [("Grouped decision", "L3126 is the decision; L3115 (task 10.8) closes with it because every other 10.8 item is "
      "ticked; L3158 (gate line) follows it.")])
h("What am I deciding?", 3)
para("How many authors NarratIQ may take on per pod before adding capacity. The proposal: **at most 60 authors "
     "active at the same time**, which with typical use means **about 150–200 registered authors per pod**, "
     "while **fewer than 10 %** of active authors use Tier-2 strict consistency. Re-measure before exceeding either.")
h("Why is this decision required?", 3)
para("**Current behaviour.** No limit is enforced or documented as accepted. The capacity figures are measured "
     "(table above); the scaling triggers are defined (capacity-planning.md §4: e.g. more than 40 authors routinely "
     "active, Tier-2 above 10 %, Q&A p95 > 10 s or search p95 > 1 s for a working day).")
para("**Important caveat.** The 60-active figure is measured. The 150–200 registered figure is an **estimate**: "
     "it assumes well under a third of signed-in authors are active at once, which has not been measured with "
     "real authors.")
para("**Alternatives.** Accept the proposal; set your own figures (for example, if you expect many Tier-2 users, the "
     "measured safe figure at 50 % Tier-2 is about 15 active, with a slow search tail); or wait for UAT.")
para("**Why engineering cannot choose.** The capacity numbers do not set the limit by themselves — the limit "
     "trades growth against risk, which is a business decision (capacity-planning.md: “the onboarding limit stays "
     "a product-owner decision”).")
h("Available options", 3)
options_table([
    ("A", "Accept the proposal", "60 active / ~150–200 registered per pod, Tier-2 under 10 %; re-measure before exceeding.",
     "The registered figure is an estimate; monitoring must confirm the active ratio.",
     "L3126, L3115 and L3158 ticked."),
    ("B", "Set different figures", "You write the active / registered / Tier-2 figures below; engineering documents them against the measurements.",
     "A higher figure than measured would exceed tested capacity; a lower one limits growth.",
     "Ticked with your figures."),
    ("C", "Defer until UAT / first real use", "Permitted: not a release blocker (sign-off §9). W-3 already prevents real author data.",
     "Stage 10 gate stays open; no documented limit when onboarding starts.", "Boxes stay open."),
])
recommendation("**A — Accept the proposal**, recording that the registered figure is an estimate to be confirmed "
               "from live monitoring.",
               "The 60-active figure is validated with zero errors and every target met; the Tier-2 condition keeps "
               "the system inside measured territory; the scaling triggers fire at 40 active, before the limit, "
               "giving lead time.")
owner_answer(["A Accept proposal", "B Different figures (write below)", "C Defer"])
blank_line("If B: active authors / registered authors / maximum Tier-2 share")
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 4 — Operations: deletion vs loss
# --------------------------------------------------------------------------------------------
h("Decision group 4 — Operations: deletion versus data loss at startup", 1)
h("OD-05 — Telling intentional deletion apart from data loss at startup", 2)
decision_meta(
    "OD-05", "Stage 12 (remediation record)", "None",
    "None numbered; affects scripted restarts (sign-off §7 rollback readiness)",
    "**Can be answered now.** On 2026-10-05 you chose “no permanent decision yet” and preserved the synthetic "
    "backup sets; this asks for the permanent handling.")
h("What am I deciding?", 3)
para("How NarratIQ should tell the difference, when it starts, between **“the data was deleted on purpose”** "
     "and **“the data was lost”**.")
h("Why is this decision required?", 3)
para("**Current behaviour.** The start script (scripts/startup_backup.sh; docs/operations/backup-and-restore.md "
     "§4a) refuses to start — “UNEXPECTED EMPTY DATABASE — STARTUP ABORTED” — when the live "
     "database has no author rows **and** a valid backup shows author data existed. This protects against a pod "
     "restart that silently wipes the database (it has happened before). But it cannot tell a deliberate deletion "
     "(for example a test author removed through account deletion) from a loss, so it also blocks after legitimate "
     "deletions. Today the only way past it is a one-time acknowledgement phrase typed by the operator on the "
     "command line, needed again at every start while those backups remain.")
para("**Right now:** the current pod has **no backups** (no /workspace/backups directory, checked 2026-10-06), so "
     "the guard is not blocking. It will matter again as soon as backups hold author data and the database later "
     "comes up empty.")
para("**Alternatives (from the checklist):**")
bullet("**(a)** a non-identifying account-deletion record kept in the database, plus hashed account ids in the "
       "backup manifest (manifest version 2). Needs a database migration and a decision on how long deletion "
       "records are kept.")
bullet("**(b)** an operator places a “.disposable” marker file next to a backup set to say “this set's data "
       "was deliberately removed; it is not evidence of loss”.")
para("**Why engineering cannot choose.** Option (a) creates a new kind of retained record about deleted accounts "
     "(a data-retention and privacy decision); option (b) places trust in an operator action. Both are product and "
     "data-retention choices.")
h("Available options", 3)
options_table([
    ("A", "In-database deletion record + hashed ids in manifest v2", "Startup can prove automatically that every author in the backup was deliberately deleted.",
     "Migration and manifest change before/after release; new retained data needs a retention period and privacy review.",
     "L3487 ticked when built and tested; retention policy updated."),
    ("B", "Operator ‘.disposable’ marker per backup set", "An operator marks specific sets as deliberately disposable; the guard ignores them and still protects every other set.",
     "Relies on the operator marking the right set; a wrong marker could hide a real loss for that set.",
     "L3487 ticked when built, tested and documented in the runbook."),
    ("C", "Keep current behaviour", "Permitted (not a release blocker): every start after a deliberate deletion needs the acknowledgement phrase.",
     "Repeated manual overrides; a habit of overriding could mask a real loss.", "L3487 stays open."),
])
recommendation("**B — Operator ‘.disposable’ marker per backup set**, with option A kept as a later option "
               "if many real authors make an all-deleted database plausible.",
               "The guard only fires when the **whole** database has no authors, which in practice is a test or "
               "fresh pod — the case that has actually occurred. A per-set marker is small, needs no migration "
               "and no new retained personal data, and keeps the protection for every unmarked set. Option A is "
               "sounder for a busy production system but costs a migration and a retention decision for a rare "
               "event.")
owner_answer(["A Deletion record + manifest v2", "B .disposable marker", "C Keep current behaviour"])
blank_line("If A: how long should deletion records be kept?")
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 5 — Release records
# --------------------------------------------------------------------------------------------
h("Decision group 5 — Release records (Stage 12)", 1)
h("OD-06 — Record accepted known issues (final list)", 2)
decision_meta(
    "OD-06", "Stage 12 (task 12.3)",
    "All accepted items: CAST-H8, CAST-H10, AWT-G, CAST-H6, PA-C6, PA-H12 (and any you accept in pending reviews)",
    "Gate 9 (task 12.3 release approval)",
    "**Answer after** the remaining human reviews (Human Review Package: A2 re-validation, A3, A4/OD-01, A5, A6, "
    "G6–G8) are decided. The box itself says it “stays open until the remaining human reviews are decided”.")
h("What am I deciding?", 3)
para("How the final list of **known issues you accept for v3.3.0** gets confirmed before it is published with the "
     "release.")
h("Why is this decision required?", 3)
para("**Current behaviour.** The accepted issues so far are recorded in the sign-off record §3 and the release "
     "notes §2/§5 (D-8 60-chapter ceiling, CAST-H8, CAST-H10, AWT-G, CAST-H6, PA-C6, PA-H12, S1–S6, "
     "presence-label loss). The human reviews still pending can add more accepted limitations.")
para("**Why engineering cannot choose.** An accepted known issue is your acceptance by definition; engineering can "
     "only transcribe it.")
h("Available options", 3)
options_table([
    ("A", "Engineering appends and ticks", "Engineering appends every acceptance you give in the pending reviews and ticks the box when none is undecided.",
     "You do not see the consolidated list before it is marked complete.", "L3398 ticked by engineering at that point."),
    ("B", "You confirm the final list", "Engineering prepares the consolidated list; the box is ticked only after you confirm it in writing.",
     "One extra short review step.", "L3398 ticked on your confirmation."),
])
recommendation("**B — You confirm the final list.**",
               "The list is what authors will be told; one consolidated read-through before publishing catches "
               "omissions and costs a few minutes.")
owner_answer(["A Engineering appends and ticks", "B I confirm the final list"])
owner_notes()

h("OD-07 — Stage 12.1 final decision package (roll-up box)", 2)
decision_meta(
    "OD-07", "Stage 12 (12.1 release gate verification record)",
    "Through its contents: G1 (A2), G3 (A1/A3), G5 (A4), G6–G8, UI-H12 and the external items",
    "Gates 3b, 4, 6 and 9 through its contents",
    "**Can be answered now** (it decides only how the box closes, not its contents).")
h("What am I deciding?", 3)
para("This box is a **container**, not a separate decision. It closes when everything it lists is complete. You "
     "only decide whether it may close automatically when its contents are done, or whether you want to approve its "
     "closure separately.")
h("Why is this decision required?", 3)
para("**Current state of its contents** (owner-decisions.md, 2026-10-05):")
table(["Listed item", "Where it is handled", "Owner decision here?"], [
    ["B1–B4, S1–S6, presence, W-1, W-2, W-4", "Decided 2026-10-05", "No (already decided)"],
    ["A1 blind review", "Recorded PASS 2026-10-05", "No"],
    ["A2 Light vs Strong re-validation; A3; A5; A6; G7; G8", "Human Review Package (pass rules: OD-11 – OD-20)", "No — human reviews (their pass rules: yes, OD-11 – OD-20)"],
    ["G6 Suggestions", "OD-09 (feature has no way in from the studio) and HR-11 / OD-16", "Yes — OD-09, OD-16"],
    ["A4 MV-5.14-D", "OD-01 (after the Story Audit reading)", "Yes — OD-01"],
    ["MV-10.8 onboarding limit", "OD-04", "Yes — OD-04"],
    ["Deletion-vs-loss handling", "OD-05", "Yes — OD-05"],
    ["UAT; multi-hour session; translation; legal", "Real authors / fluent speaker / counsel", "No — external or human"],
    ["W-3 off-pod backup; W-5 SECRET_KEY copy", "Standing conditions (context section)", "No — infrastructure / your confirmation"],
], widths_cm=[6.0, 6.0, 4.5])
para("**Note on the box text.** Its second dated note still says “B1–B4 … S1–S6 … still open”. "
     "That is superseded by the first note and owner-decisions.md (all decided 2026-10-05). Engineering should "
     "correct that wording when the box is next updated; nothing is re-asked here.")
h("Available options", 3)
options_table([
    ("A", "Close automatically", "Engineering ticks it when every listed item above is recorded as decided or completed.",
     "None material — each item already carries its own decision or review.", "L3509 ticked at that point."),
    ("B", "Approve closure separately", "Engineering reports when the contents are complete; you approve closing it.",
     "One more approval round.", "L3509 ticked on your approval."),
])
recommendation("**A — Close automatically.**",
               "Every item in it already needs its own decision or review, so a separate approval of the container "
               "would only repeat them.")
owner_answer(["A Close automatically", "B I approve closure separately"])
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 6 — Project completion
# --------------------------------------------------------------------------------------------
h("Decision group 6 — Final project completion", 1)
h("OD-08 — Is ‘AI quality improvement demonstrated by measurement’ satisfied?", 2)
decision_meta(
    "OD-08", "Final Project Completion Checklist",
    "AWT-G (Critical, accepted B1 — criterion NOT MET); AWT-D, AWT-I, AWT-1.2, 1.6, 3.7 (A2/G1, re-validation pending)",
    "Final Project Completion; depends on Gate 3b",
    "**Answer after** Gate 3b human re-validation (A2 Light vs Strong on post-fix outputs) if you choose B; option A "
    "can be chosen now.")
h("What am I deciding?", 3)
para("Whether the final-checklist line “AI quality improvement demonstrated by measurement against the Stage 5 "
     "baseline” is satisfied by what has been measured, or must wait for the remaining human re-validation.")
h("Why is this decision required?", 3)
para("**The evidence is mixed:**")
bullet("**For:** the Stage 5 golden-set measurement against the 5.2 baseline is recorded (Stage 5 gate line "
       "“Measured improvement over the 5.2 baseline recorded” is ticked): text similarity rose in 11/12 "
       "scenarios, content similarity in 12/12, suggestions recall 0.80 → 1.00. Your A1 blind review: v4 "
       "preferred 5, v2 3, no difference 4 (PASS).")
bullet("**Against:** run-to-run consistency (AWT-G) is now **worse than the Stage 5 baseline** — mean variation "
       "0.0866 vs 0.0643 (docs/testing/stage-12/stage-12.1/awt-g-consistency.md); you accepted it as a known "
       "limitation (B1) but it remains NOT MET. A2 Light vs Strong **failed** your review (5/12), was fixed, and "
       "awaits human re-validation.")
para("**Why engineering cannot choose.** Whether a mixed record “demonstrates” improvement is a judgement "
     "about the meaning of the line; engineering must not rewrite a not-met criterion as a pass.")
h("Available options", 3)
options_table([
    ("A", "Satisfied now by the recorded measurements", "The line is ticked citing 5.16 and A1, with AWT-G and A2 recorded as exceptions.",
     "Ticks a completion line while one baseline metric is worse and A2 is unvalidated.", "L3558 ticked with the exceptions noted."),
    ("B", "Wait for Gate 3b re-validation", "Ticked only after A2 re-validation (and Gate 3b) is recorded.",
     "Project completion waits on a human review that is already required for Gate 3b.", "L3558 stays open until then."),
])
recommendation("**B — Wait for Gate 3b re-validation.**",
               "One metric measured against the Stage 5 baseline is worse, and the A2 failure has a fix that no human "
               "has yet judged. Waiting costs nothing extra because Gate 3b needs that re-validation anyway, and it "
               "keeps the completion record free of a qualified pass.")
owner_answer(["A Satisfied now", "B Wait for Gate 3b"])
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 7 — Product scope: Writing Suggestions
# --------------------------------------------------------------------------------------------
h("Decision group 7 — Product scope: Writing Suggestions (Stage 12, new 2026-10-06)", 1)
h("OD-09 — Writing Suggestions has no way in from the studio: restore, retire or defer", 2)
decision_meta(
    "OD-09", "Stage 12 (12.3 record; feature from Stage 5 task 5.13)",
    "G6: SUG-C1, SUG-C2 (Critical); SUG-H3, H4, H5, H6, H7, H8, H10, H11 (High) — 10 issues",
    "Gate 4 (G6, 2 Critical + 8 High of the 75 undecided); Gate 3b (5.13 author review, A6)",
    "**Can be answered now.** Answer it before the G6 review (HR-11 / OD-16), because it decides whether that review "
    "can be done in the product.")
h("What am I deciding?", 3)
para("Whether NarratIQ's **Writing Suggestions** feature (developmental-editor style notes on a chapter) should be "
     "**put back into the studio** so authors can use it, **retired** from the product, or **left unreachable for "
     "this release** and fixed afterwards.")
h("Why is this decision required?", 3)
para("**Current behaviour (found 2026-10-06 while building the human review package, verified in code).** Authors "
     "cannot reach the feature at all:")
bullet("The frontend function that calls it, aiApi.suggestions (frontend/lib/api.ts), has **no caller** anywhere in "
       "the app.")
bullet("The last screen that used it was removed by commit 34dc303 (“ui/ux update”, 2026-06-12) — "
       "**before** the Stage 5 overhaul of suggestions (task 5.13). That overhaul was verified at the API level only "
       "(POST /api/ai/suggestions works live), never in the studio.")
bullet("There is no entry for it in the studio tool registries (frontend/lib/registries/).")
bullet("The product specification (docs/specifications/narratiq-ai-product-and-technical-documentation.md, about "
       "line 51) lists “Writing suggestions — ✅ Overhauled in Stage 5” as delivered.")
bullet("The earlier owner guide told you to review G6 “in the AI sidecar → Suggestions”; that screen "
       "does not exist. The G6 issues can therefore only be reviewed on **saved outputs** (HR-11), never in the "
       "product or in UAT.")
bullet("A sweep of every client API function found no other author-facing AI feature without a caller.")
para("**Why engineering cannot choose.** Where a tool lives in the studio, and whether a feature ships at all, are "
     "product decisions (Stage 8 information architecture). Engineering did not change it.")
h("Available options", 3)
options_table([
    ("A", "Restore it as a studio tool", "Engineering adds one tool home (docs/architecture/adding-a-studio-tool.md), a sidecar panel and studio tests. G6 is then reviewed in the product and in UAT.",
     "A small UI change late in the release candidate; it is covered by the W-1 regression on the release commit, which is needed anyway.",
     "New owner box ticked as “restore”; G6 reviewed live (HR-11 / OD-16); spec stays correct."),
    ("B", "Retire the feature", "Record the retirement; correct the specification and release notes; the Stage 5 work is not offered to authors.",
     "Loses an overhauled, measured feature (recall 0.80 → 1.00, priorities 0 % → 100 %). The 10 SUG issues still need your disposition (e.g. closed as not applicable).",
     "Box ticked as “retire”; SUG-* need a recorded owner disposition; spec corrected."),
    ("C", "Defer the UI to after release", "Release without a way in; G6 judged on saved outputs (HR-11) only; restore after release.",
     "A feature listed as delivered is unavailable; UAT cannot cover it; the spec and release notes must say so. Use only if you judge the release requirements allow it.",
     "Box ticked as “defer” with a post-release follow-up; G6 decided on saved outputs; spec/release notes corrected."),
])
recommendation("**A — Restore it as a studio tool.**",
               "It is an author-facing feature that was overhauled and measured in Stage 5 and is documented as "
               "delivered. Restoring it is small, follows an existing documented recipe, keeps the Stage 5 "
               "investment, and lets G6 be judged the way the checklist intends — by using the product.")
owner_answer(["A Restore", "B Retire", "C Defer UI to after release"])
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 8 — Testing: AI quality regression alarm rule
# --------------------------------------------------------------------------------------------
h("Decision group 8 — Testing: the AI-quality regression alarm (Stage 6)", 1)
h("OD-10 — Approve the AI-quality regression alarm rule", 2)
decision_meta(
    "OD-10", "Stage 6 (task 6.5, AI quality evaluation harness)", "None directly (protects the accepted AWT and SUG results)",
    "Stage 6 task 6.5 (not a sign-off §9 blocker)",
    "**Can be answered now.** The live proof run may still be in progress; see “Live proof” below.",
    [("Related but technical", "The 6.5 parent box and its verification line “A deliberate prompt regression is "
      "detected by the harness” are engineering items; they close on the live proof, not on this decision.")])
h("What am I deciding?", 3)
para("Whether you **agree to the rule** that decides when automated AI-quality checks raise an alarm. The checklist "
     "asks for an alarm “beyond an **agreed** threshold”, so the threshold needs your agreement.")
h("Why is this decision required?", 3)
para("**The problem the rule solves.** The AI model is not perfectly repeatable. A single failed check proves "
     "nothing: one known case (adventure-3 “already suitable”) fails about 1 run in 10 on unchanged code "
     "(awt-g-consistency.md). Before 2026-10-06 the harness checked each rule once, so it could not tell a real "
     "regression from normal wobble; the box was left open for that reason (Stage 9 reconciliation).")
para("**What engineering built (backend/tests/ai_quality_regression_gate.py):**")
bullet("**What is measured:** each of the 11 harness checks is run **20 times** live and scored as a pass count: "
       "locked sentence kept byte-identical (3 passages); “already suitable” passage left unchanged (4); "
       "character names preserved (2); Light strength not flagged as too heavy (1); suggestions structurally valid (1).")
bullet("**Alarm rule:** ALARM when a check's pass rate is **lower** than a recorded baseline of the same code, and "
       "the drop is too large to be chance: one-sided Fisher exact test p < 0.01 / 11 (a 1-in-100 chance that a whole "
       "run raises a false alarm). A rate equal to or above the baseline never alarms.")
bullet("**In plain numbers:** if a check passed 20/20 in the baseline it alarms at 11/20 or fewer; 18/20 → alarms "
       "at 7/20 or fewer; 14/20 → at 3/20 or fewer. It detects a **collapse**, not the documented 1-in-10 wobble.")
para("**Honest note on the box wording.** The box says “against the recorded Stage 5 baseline”. The rule "
     "compares against a baseline recorded on the **current** code with the same 20-trial method. The Stage 5 "
     "baseline used 3 trials on older prompts and is no longer representative (AWT-G). Approving option A also "
     "approves this substitution.")
h("Live proof", 3)
for line in GATE_RESULT_LINES:
    bullet(line)
para("**Alternatives.** Approve as is; make it stricter (catch smaller drops, at the cost of more false alarms "
     "and/or more GPU time); or set your own rule.")
para("**Why engineering cannot choose.** The trade-off between missed regressions and false alarms is a risk "
     "appetite question, and the checklist explicitly requires an agreed threshold.")
h("Available options", 3)
options_table([
    ("A", "Approve the rule as is", "N = 20 trials, family-wise false-alarm rate 1 %, compared with a same-code baseline.",
     "Moderate drops (e.g. 20/20 → 14/20) do not alarm.", "6.5 “agreed threshold” box ticked once the live proof is recorded."),
    ("B", "Require a stricter rule", "For example family-wise 5 % (about 1 clean run in 20 alarms falsely) and/or N = 40 (about twice the GPU time).",
     "More false alarms to investigate and/or longer runs before each release.", "Box ticked after engineering re-runs the proof with your rule."),
    ("C", "Other (write it below)", "Your own rule.", "Depends on the rule.", "Box ticked after re-running with your rule."),
])
recommendation("**A — Approve the rule as is.**",
               "It models the model's own variability instead of ignoring it, raises a false alarm about once in a "
               "hundred full runs, and still catches the kind of failure that matters (a prompt or code change that "
               "breaks a guarantee). A stricter rule mainly buys more false alarms on a non-deterministic model.")
owner_answer(["A Approve as is", "B Stricter rule", "C Other (write below)"])
blank_line("If B or C: the rule you want")
owner_notes()
page_break()

# --------------------------------------------------------------------------------------------
# GROUP 9 — Review acceptance rules (supporting decisions)
# --------------------------------------------------------------------------------------------
h("Decision group 9 — Review acceptance rules (supporting decisions — no checklist box of their own; they decide how "
  "the human results close the D-6 items)", 1)
para("The Human Review Package (NarratIQ_Human_Review_Package.docx) marks several pass rules **“OWNER THRESHOLD "
     "REQUIRED — see Owner Decision Package (…)”**. Each reference is answered here. **Answer these before "
     "the human review if you can**, so reviewers know the bar in advance and results cannot be read to fit them.")
para("Severity answers in the reviews use the scale **None / Minor / Major / Blocking**. Closing an issue as "
     "“accepted” always means it is recorded as an accepted known issue (OD-06).")
table(["Reference in the Human Review Package", "Answered by"], [
    ["(G3) HR-01 – HR-05", "OD-11"], ["(G1) HR-06 exactly 6/12", "OD-12"], ["(G1 / A15 thresholds) HR-07", "OD-13"],
    ["(A3) HR-08", "OD-14"], ["(G5) HR-09; MV-5.14-D", "OD-15; OD-01"], ["(G6) HR-11", "OD-16; OD-09"],
    ["(G7) HR-12", "OD-17"], ["(G8) HR-13, HR-14, HR-15", "OD-18"],
    ["(A6) HR-17; (A6 / 7.12) HR-18; (A6 / 5.10) HR-19", "OD-19"], ["(11.7) HR-20", "OD-20"],
], widths_cm=[10.0, 6.5])

SEV_OPTIONS = [
    ("A", "Per-issue: None/Minor close; Major/Blocking stay open", "An issue closes as accepted when its worst recorded severity is None or Minor (Minor recorded as a known limitation). Major stays open unless you accept it by name; Blocking stays open as work.",
     "Minor weaknesses ship as documented known issues.", "Each D-6 issue closes or stays open individually."),
    ("B", "Stricter: only None closes", "Any Minor, Major or Blocking keeps the issue open.",
     "More issues stay open; release may wait on polish.", "Fewer D-6 issues close."),
    ("C", "Lenient: anything but Blocking closes", "Major is accepted automatically as a known limitation.",
     "Significant problems may ship without a named acceptance.", "More D-6 issues close."),
]
SEV_WHY = ("It follows D-6 issue by issue, uses the issue IDs already printed on each question, keeps clear problems "
           "open, and still requires your explicit acceptance before a Major problem ships.")


def support(od, title, refs, quote, d6, gate, when, what, why_paras, options, rec, why, answers, extra=None):
    h(f"{od} — {title}", 2)
    decision_meta(od, "Supporting rule (Human Review Package " + refs + ")", d6, gate, when, extra)
    h("What am I deciding?", 3)
    para(what)
    h("Why is this decision required?", 3)
    para("**What the Human Review Package says (quoted):** " + quote)
    for wp in why_paras:
        para(wp)
    h("Available options", 3)
    options_table(options)
    recommendation(rec, why)
    for label, choices in answers:
        owner_answer(choices, label)
    owner_notes()


WHEN_BEFORE = "**Can be answered now — recommended before the human review** so reviewers know the bar."

support("OD-11", "Rule: how the G3 rewrite-quality issues close", "HR-01 – HR-05, HR-08",
        "“Existing criterion: none exists for an ABSOLUTE review. The only recorded criterion for G3 is MV-5.BR's "
        "comparative rule (‘current version preferred or equal on style; no transform clearly worse’), which "
        "A1 met; the owner directed that A1 alone does not close G3.” — “Mapping: OWNER THRESHOLD "
        "REQUIRED — see Owner Decision Package (G3). … Any answer of ‘Blocking’, or ‘Reject’ "
        "in the summary, must be reported to the owner with the item number.”",
        "AWT-A, AWT-B, AWT-E, AWT-F, AWT-H, AWT-J (Critical); tone 1.1, 1.3–1.5; emotion 2.1–2.3, 2.6, 2.7; "
        "audience 3.1–3.3, 3.5; style 4.1, 4.2, 4.4–4.10 (High) — 6 Critical + 22 High",
        "Gate 3b and Gate 4 (G3)", WHEN_BEFORE,
        "What result in the absolute rewrite reviews (HR-01 to HR-04, the per-Critical verdicts in HR-05, and the "
        "children's review HR-08 for the audience items) closes each G3 issue.",
        ["The owner guide's G3 rule was “your 2A result (+ 2C for audience) — pass → close; fail → "
         "named transforms need work”. 2A was the blind review (A1). On 2026-10-06 you directed that A1 alone does "
         "not close G3, so the absolute review needs its own closing rule. This decision does not re-open that "
         "direction."],
        [("A", "Per-issue rule", "Each Critical closes when HR-05 says Accept for it and no answer tagged with it in HR-01–HR-04/HR-08 is ‘Blocking’. Each High closes when its transform's summary (HR-0x.SUM) is Accept and no answer tagged with it is ‘Blocking’. Otherwise it stays open and the named transform needs work (or you accept it by name).",
          "Relies on careful tagging (already printed on each question).", "Issues close individually."),
         ("B", "Transform-level rule", "A transform's summary Accept closes all its High issues; Criticals follow HR-05 only.",
          "A Blocking answer on one issue can be hidden by an overall Accept.", "Issues close per transform."),
         ("C", "All-or-nothing", "G3 closes only if every HR-01–HR-05 answer is Accept and nothing is Blocking; otherwise all 28 stay open.",
          "One weak item holds all 28 open.", "G3 closes as a block or not at all.")],
        "**A — Per-issue rule.**",
        "D-6 counts issues individually; the per-issue rule closes exactly what the reviewer accepted, keeps anything "
        "marked Blocking open, and never lets a summary hide a specific problem.",
        [("OD-11 G3 closure rule", ["A Per-issue", "B Transform-level", "C All-or-nothing"])])

support("OD-12", "Rule: G1 Light re-validation result of exactly 6 out of 12", "HR-06",
        "“‘Most’ is not given a number in the source. A2's 5/12 was recorded as FAIL. Therefore: 7 or more "
        "of 12 → PASS (G1 becomes accepted-limitation candidates for the owner's confirmation); 5 or fewer → "
        "FAIL (technical work); exactly 6 of 12 → OWNER THRESHOLD REQUIRED — see Owner Decision Package "
        "(G1).”",
        "AWT-D, AWT-I (Critical); AWT-1.2, AWT-1.6, AWT-3.7 (High) — the G1 group",
        "Gate 3b (A2 re-validation) and Gate 4 (G1)", WHEN_BEFORE,
        "What happens if exactly 6 of the 12 tone and age-adaptation pairs are judged both acceptable and lighter "
        "than Strong after the Light repair.",
        ["The existing rule (owner-decision-guide.md 2B) uses the word “most” without a number. Even a PASS "
         "only makes the five issues candidates for your acceptance; it does not close them by itself."],
        [("A", "6/12 counts as FAIL", "“Most” means more than half; a tie is not most.",
          "A borderline result leads to more technical work.", "G1 stays open; engineering continues on Light."),
         ("B", "6/12 counts as PASS", "Half is enough to make the issues acceptance candidates.",
          "Half the pairs may still be too heavy or not lighter.", "G1 becomes acceptance candidates."),
         ("C", "Split rule", "6/12 passes only if tone and age adaptation each reach at least 3 of 6.",
          "More complex; still borderline.", "Depends on the split.")],
        "**A — 6/12 counts as FAIL.**",
        "It reads “most” in its ordinary meaning, matches how A2's 5/12 was treated, and puts the burden on "
        "the repair to show a clear improvement.",
        [("OD-12 G1 tie rule", ["A FAIL at 6/12", "B PASS at 6/12", "C Split rule"])])

support("OD-13", "Rule: Light warning/retry level from the reviewers' labels (A15)", "HR-07",
        "Box text: “label about 60–100 Light outputs as acceptable or not, then decide warning/retry levels "
        "(until then no automatic action …)”. — “Deciding the warning/retry levels from the labels "
        "is engineering analysis plus an owner decision: OWNER THRESHOLD REQUIRED — see Owner Decision Package "
        "(G1 / A15 thresholds).”",
        "AWT-D, AWT-I, AWT-1.2, AWT-1.6, AWT-3.7 (G1, supporting evidence)",
        "Gate 3b / Gate 4 (G1, supporting)", WHEN_BEFORE,
        "How the 75 labels (60 in HR-07 plus 15 in HR-06) are turned into the level at which a Light rewrite is "
        "retried and, if still too heavy, shown with the amber “too heavy” note.",
        ["Today the level is a new-word share above **0.45** (LIGHT_NEW_SHARE_MAX), set on 2026-10-05 from only 15 "
         "labels: every accepted Light edit was at or below 0.438; above 0.45, 4 of 6 rejected and none of 9 accepted. "
         "It cut age-adaptation Light outputs over the level from 51 % to 14 % and tone from 32 % to 20 %."],
        [("A", "Derive from your labels; you approve the number", "Engineering finds the level that best separates ‘Acceptable’ from ‘Too much’ on all 75 labels, reports how often the note would be right and wrong, and changes the level only after you approve it.",
          "One short extra approval.", "A15 box closes with the approved level."),
         ("B", "Keep 0.45", "The labels are used only to report how well 0.45 agrees with readers.",
          "If the labels disagree, the warning stays miscalibrated.", "A15 box closes with 0.45."),
         ("C", "Favour catching heavy edits", "Pick the level that warns on at least 90 % of ‘Too much’ labels, accepting more false warnings.",
          "Authors see the amber note more often on edits that are fine.", "A15 box closes with that level.")],
        "**A — Derive from your labels; you approve the number.**",
        "75 labels are five times the evidence behind 0.45; using them is the purpose of the A15 box, and keeping "
        "the final number with you avoids engineering silently retuning a product behaviour.",
        [("OD-13 A15 level", ["A Derive and approve", "B Keep 0.45", "C Favour catching"])])

support("OD-14", "Rule: tolerance in the children's meaning review (A3)", "HR-08",
        "Box text: “a manual read of the children's rewrites (grief and euphemism fixtures) that every difficult "
        "event is kept and not changed.” — “Strict reading of the box: PASS only if every reviewed "
        "rewrite is ‘Kept’. Any ‘Changed’ → FAIL. No tolerance for exceptions is recorded; if "
        "the owner wants to allow some, OWNER THRESHOLD REQUIRED — see Owner Decision Package (A3).”",
        "AWT-3.1, 3.2, 3.3, 3.5 (High, G3 audience); with A1/A3 also AWT-A, B, E, F, H, J",
        "Gate 3b (A3) and Gate 4 (G3 audience)", WHEN_BEFORE,
        "Whether any “Changed” meaning among the 16 children's rewrites can be tolerated.",
        ["The risk is a death or grief event softened into a different meaning (for example “went away”) "
         "in a children's version. No automated check measures meaning; the author still sees the rewrite before "
         "Replace."],
        [("A", "Strict: every rewrite ‘Kept’", "Any ‘Changed’ fails the review.",
          "One borderline case means more work on children's rewrites.", "A3 passes only with 16/16 Kept."),
         ("B", "Tolerate at most 1 of 16", "One ‘Changed’ is allowed if you judge it minor; it is recorded as a known limitation.",
          "A real meaning change can ship.", "A3 passes with 15/16 or better."),
         ("C", "Case by case", "Each ‘Changed’ is shown to you; you decide per case.",
          "Slower; the outcome depends on judgement after seeing results.", "A3 passes when you clear each case.")],
        "**A — Strict: every rewrite ‘Kept’.**",
        "It is the box's literal requirement, and changing the meaning of a death for a child reader is exactly the "
        "harm the review exists to catch; any such case is a real defect worth fixing.",
        [("OD-14 A3 tolerance", ["A Strict", "B At most 1 of 16", "C Case by case"])])

support("OD-15", "Rule: G5 Story Audit per-issue closure", "HR-09",
        "“For the ten D-6 issues: OWNER THRESHOLD REQUIRED — see Owner Decision Package (G5) (owner guide: "
        "‘accept → close; reject → named follow-ups’). Any ‘Blocking’ answer must be "
        "reported with the finding.”",
        "AUDIT-C1–C5 (Critical); AUDIT-H6–H10 (High)", "Gate 3b (A4) and Gate 4 (G5)",
        WHEN_BEFORE + " It sets the rule you apply when answering OD-01 line (4).",
        "Which per-issue verdicts from the Story Audit reading close each of the ten G5 issues.",
        ["HR-09 records a severity verdict for each of the ten issues. MV-5.14-D (accept / accept with follow-up / "
         "reject for the three 5.14 items) is OD-01; keep the two consistent (AUDIT-C4 ↔ timeline, AUDIT-C5 "
         "↔ narrative)."],
        SEV_OPTIONS, "**A — None/Minor close; Major/Blocking stay open.**", SEV_WHY,
        [("OD-15 G5 per-issue rule", ["A None/Minor close", "B Only None closes", "C All but Blocking close"])])

support("OD-16", "Rule: G6 Suggestions per-issue closure", "HR-11",
        "Box rule: “box PASS if HR-11.W.Q6 = YES, FAIL if NO.” — “For the ten G6 issues: OWNER "
        "THRESHOLD REQUIRED — see Owner Decision Package (G6) (owner guide: ‘accept or name the "
        "weakness’).”",
        "SUG-C1, SUG-C2 (Critical); SUG-H3–H8, H10, H11 (High)", "Gate 4 (G6)",
        WHEN_BEFORE + " Depends on OD-09: if you retire the feature (OD-09 B), this rule is not used and the SUG "
        "issues need your disposition instead.",
        "Which per-issue verdicts from the Suggestions review close each of the ten G6 issues.",
        ["Today the review can only use saved outputs, because the feature has no way in from the studio (OD-09)."],
        SEV_OPTIONS, "**A — None/Minor close; Major/Blocking stay open.**", SEV_WHY,
        [("OD-16 G6 per-issue rule", ["A None/Minor close", "B Only None closes", "C All but Blocking close"])])

support("OD-17", "Rule: G7 Plot Assistant — ‘Partly correct’ answers and per-issue closure", "HR-12",
        "“PASS if Q1–Q6 are ‘Correct’ and Q7 is answered as not in the manuscript; any "
        "‘Incorrect’ or ‘Invented’ → FAIL; ‘Partly correct’ → OWNER THRESHOLD "
        "REQUIRED (G7).” — “Per-issue closure: OWNER THRESHOLD REQUIRED — see Owner Decision "
        "Package (G7).”",
        "PA-C1, PA-C9 (Critical); PA-H10, H11, H13 (High)", "Gate 4 (G7)", WHEN_BEFORE,
        "(1) How a “Partly correct” Plot Assistant answer counts, and (2) which per-issue verdicts close "
        "each G7 issue.",
        ["You already accepted that broad questions can miss the key passage (B4, PA-H12) and that ordering is "
         "imperfect (B3, PA-C6). A “Partly correct” answer is typically incomplete rather than wrong."],
        [("A", "(1) Incomplete-but-not-wrong passes", "‘Partly correct’ counts as a pass if nothing stated is wrong and the reviewer notes what is missing; anything wrong is ‘Incorrect’. (2) Per-issue: None/Minor close; Major/Blocking open.",
          "Incomplete answers ship as a documented limitation (consistent with B3/B4).", "G7 issues close individually."),
         ("B", "(1) Partly = FAIL", "Any ‘Partly correct’ fails Q2. (2) Only None closes.",
          "Likely keeps G7 open on incompleteness you have already accepted elsewhere.", "Fewer G7 issues close."),
         ("C", "(1) Case by case", "Each ‘Partly’ answer is shown to you. (2) Lenient: all but Blocking close.",
          "Outcome decided after seeing results.", "Depends.")],
        "**A for both parts.**",
        "Wrong or invented answers still fail, which is what damages an author's trust; incompleteness matches "
        "limitations you have already accepted, and the per-issue rule keeps clear problems open.",
        [("OD-17 (1) ‘Partly correct’", ["A Passes if nothing wrong", "B FAIL", "C Case by case"]),
         ("OD-17 (2) G7 per-issue rule", ["A None/Minor close", "B Only None closes", "C All but Blocking close"])])

support("OD-18", "Rule: G8 Studio UI per-issue closure", "HR-13, HR-14, HR-15",
        "HR-13: “Per-issue closure (UI-C1, C2, H9, H14): OWNER THRESHOLD REQUIRED — see Owner Decision "
        "Package (G8) (owner guide: ‘accept, or name the friction’).” HR-14 and HR-15: “Per-issue "
        "closure: OWNER THRESHOLD REQUIRED — see Owner Decision Package (G8).”",
        "UI-C1, UI-C2, UI-C6 (Critical); UI-H9, H10, H11, H13, H14 (High). UI-H12 is not covered (multi-hour session).",
        "Gate 4 (G8)", WHEN_BEFORE,
        "Which per-issue verdicts from the three studio reviews close each G8 issue.",
        ["The task boxes 8.3, 8.4 and 8.5 already have YES/NO pass rules in the review; this decision covers only "
         "the D-6 issue closure."],
        SEV_OPTIONS, "**A — None/Minor close; Major/Blocking stay open.**", SEV_WHY,
        [("OD-18 G8 per-issue rule", ["A None/Minor close", "B Only None closes", "C All but Blocking close"])])

support("OD-19", "Rules: A6 thresholds for 5.15, 7.12 and 5.10", "HR-17, HR-18, HR-19",
        "HR-17 (5.15): “PASS if Q9 = YES and no metric is ‘No’; any metric ‘No’ → FAIL; "
        "‘Partly’ answers → OWNER THRESHOLD REQUIRED — see Owner Decision Package (A6).” "
        "HR-18 (7.12): “How much better ‘closely’ must score than ‘Off’ is not defined: if the "
        "reviewer is unsure, OWNER THRESHOLD REQUIRED — see Owner Decision Package (A6 / 7.12).” HR-19 (5.10): "
        "“No numeric threshold exists for the 1–5 ratings: OWNER THRESHOLD REQUIRED — see Owner Decision "
        "Package (A6 / 5.10) if the summary and the ratings disagree.”",
        "AWT-B, AWT-4.10 (G3); 5.15 has no D-6 issue of its own", "Gate 3b (A6)", WHEN_BEFORE,
        "Three small numeric rules for the remaining author reviews: analytics numbers (5.15), “match my "
        "voice” (7.12) and author identity under style (5.10).",
        ["HR-17 is also referenced as “(A6)” in the Human Review Package and is included here so every "
         "reference is answered."],
        [("A", "(1) 5.15: Partly allowed with a note — (2) 7.12: ‘closely’ rated higher in at least 2 of 3 chapters — (3) 5.10: summary governs; any item rated 1–2 is shown to you after the key is revealed",
          "(1) PASS if Q9 = YES, no ‘No’, and each ‘Partly’ has a note (recorded as a follow-up on that metric's explanation). (2) Used only if the reviewer is unsure. (3) A low rating on a Strong item can be legitimate.",
          "Some imperfect explanations or style items pass with a follow-up.", "5.15, 7.12, 5.10 boxes close on these rules."),
         ("B", "(1) Any Partly fails — (2) all 3 chapters — (3) all six ratings 3 or higher",
          "Strict versions of each rule.", "More boxes stay open on borderline readings.", "Fewer A6 boxes close."),
         ("C", "Other (write below)", "Your own numbers.", "Depends.", "Depends.")],
        "**A for each of the three.**",
        "Each keeps the reviewer's overall judgement in charge, gives a clear tie-breaker only where the reviewer is "
        "unsure, and does not penalise Strong rewrites for changing more, which is what Strong is for.",
        [("OD-19 (1) 5.15 ‘Partly’ (HR-17)", ["A Allowed with note", "B Any Partly fails", "C Other"]),
         ("OD-19 (2) 7.12 style match (HR-18)", ["A 2 of 3 chapters", "B All 3 chapters", "C Other"]),
         ("OD-19 (3) 5.10 identity (HR-19)", ["A Summary governs", "B All ratings 3+", "C Other"])])

support("OD-20", "Rule: 11.7 ‘Possible imitation’ in the author-style outputs", "HR-20",
        "“PASS if all 15 are ‘No imitation’; any ‘Clear imitation’ → FAIL; any "
        "‘Possible imitation’ → OWNER THRESHOLD REQUIRED — see Owner Decision Package (11.7).” "
        "— “The box closes only together with the legal review (external, not in this package).”",
        "None (Gate 5 / 11.7 copyright-risk)", "Gate 9 prerequisite (documentation reconciled, 11.7); sign-off §9 item 5",
        WHEN_BEFORE,
        "What happens if a reviewer marks one of the 15 saved author-style outputs as “Possible imitation” of "
        "an in-copyright author.",
        ["Automated probes found 0/15 living authors named and 0 instructions obeyed; the human reading is still "
         "required, and the legal review of the disclaimer is separate and external."],
        [("A", "Send to legal counsel", "Each ‘Possible’ output goes to counsel with the legal review; the box closes only when counsel clears it.",
          "Waits on counsel, who is already required.", "11.7 box closes with counsel's clearance."),
         ("B", "Treat as FAIL", "Engineering hardens the author-style prompt and re-runs the probe.",
          "Work may be unnecessary if counsel would clear it.", "11.7 box stays open until a clean re-run."),
         ("C", "Treat as PASS", "Only ‘Clear imitation’ fails.", "Copyright risk accepted without legal advice.", "11.7 box can close earlier.")],
        "**A — Send to legal counsel with the legal review.**",
        "Whether a passage imitates an author too closely is a legal question; counsel is already required for "
        "11.7, so this adds no delay and avoids either over- or under-reacting.",
        [("OD-20 11.7 ‘Possible imitation’", ["A Legal counsel", "B FAIL", "C PASS"])])
page_break()

# --------------------------------------------------------------------------------------------
# FINAL SIGN-OFF — separated and blocked
# --------------------------------------------------------------------------------------------
h("FINAL RELEASE SIGN-OFF — DO NOT COMPLETE YET", 1)
para("**STATUS: BLOCKED UNTIL RELEASE PREREQUISITES PASS**", size=13, color=RGBColor(0xC0, 0x00, 0x00))
para("This section is separated from the decisions above on purpose. Do not tick, sign or date anything here until "
     "every prerequisite below shows as passed or decided. Engineering does not sign this and makes **no "
     "recommendation** on approval: the release approval is yours alone.")
h("OD-21 — Written release sign-off for v3.3.0", 2)
decision_meta(
    "OD-21", "Stage 12 (task 12.3 and the Stage 12 completion gate)", "All 114 D-6 release-blocking issues (Gate 4)",
    "Gate 9 — Release approval",
    "**Not yet.** Only after every prerequisite below is complete.",
    [("Grouped decision", "Three boxes record one act: \u201cObtain and record written sign-off\u201d (12.3), "
      "\u201cWritten sign-off recorded in the repository\u201d (12.3 verification) and \u201cProduct owner sign-off "
      "recorded\u201d (Stage 12 gate line).")])
h("Prerequisites (from sign-off record §9 and the open gates)", 3)
table(["#", "Prerequisite", "Current status"], [
    ["1", "Gate 3b — human reviews A1–A6 (A2 re-validation; A3; A4 = OD-01; A5; A6)", "OPEN"],
    ["2", "Gate 4 / D-6 — 75 undecided release-blocking issues (20 Critical / 55 High)", "OPEN"],
    ["3", "Gate 6 — W-1 full regression recorded against the exact release commit, and real-author UAT", "OPEN"],
    ["4", "W-1 regression record (docs/releases/v3.3.0-regression.md) — needs your release commit", "NOT CREATED"],
    ["5", "W-3 — no real author data until an approved off-pod backup exists and one restore from it is verified", "OPEN (no provider)"],
    ["6", "Legal review of the copyright-risk disclaimer (11.7)", "OPEN"],
    ["7", "Fluent-speaker translation review (release-blocking per your 2026-10-03 decision)", "OPEN"],
    ["8", "Multi-hour writing session (UI-H12, High)", "OPEN"],
    ["9", "Release commit and tags (v3.3.0 and the previous release as rollback target)", "NOT MADE"],
    ["10", "OD-06 accepted known issues confirmed; OD-01 decided", "PENDING"],
    ["11", "OD-09 (Writing Suggestions) and the review pass rules OD-11 – OD-20 decided", "PENDING"],
    ["12", "Gate 9 — this record signed", "NOT GIVEN"],
    ["—", "Also standing: W-5 owner confirmation that SECRET_KEY is copied to a separate secret store", "OPEN"],
], widths_cm=[1.0, 11.5, 4.0])
para("Prerequisite completion (to be filled in only when each is actually complete):")
for i in range(1, 13):
    doc.add_paragraph(f"{BOX} Prerequisite {i} complete — evidence: ______________________________________")
h("Sign-off block (mirrors docs/releases/v3.3.0-sign-off.md §10) — DO NOT COMPLETE YET", 3)
para("**STATUS: BLOCKED — PREREQUISITES NOT COMPLETE.**", color=RGBColor(0xC0, 0x00, 0x00))
owner_answer(["Approved", "Not approved"], "OWNER ANSWER — OD-21 (BLOCKED)")
para("**Owner's current position (2026-10-06):** " + OD21_POSITION)
para(RECORDED_LINE, size=9)
blank_line("Release commit")
blank_line("Conditions (if any)")
blank_line("Name")
blank_line("Role")
blank_line("Date (UTC)")
blank_line("Written approval (verbatim)")
page_break()

# --------------------------------------------------------------------------------------------
# Completion summary
# --------------------------------------------------------------------------------------------
n_boxes = len(BOXES)
n_open = len([b for b in BOXES if b[2] not in CLOSED_BOXES])
blocking = [r[0] for r in SUMMARY if r[4] == "YES"]
nonblocking = [r[0] for r in SUMMARY if r[4] == "NO"]
n_answer_lines = len(ANSWER_LINES)
h("OWNER DECISION COMPLETION SUMMARY", 1)
table(["Measure", "Count"], [
    ["Owner-decision boxes represented (open + already decided)", f"{n_boxes} ({n_open} open + {n_boxes - n_open} already decided: L3531 cast test, closed 2026-10-06)"],
    ["Open owner-decision boxes", f"{n_open} (19 from the previous reconciliation still open + the new Suggestions box + task 6.5 \u2018agreed threshold\u2019)"],
    ["Decisions presented", f"{len(SUMMARY)}: {len(BOX_DECISIONS)} with checklist boxes (OD-01 \u2013 OD-10, OD-21) + {len(SUPPORTING)} supporting review rules without a box (OD-11 \u2013 OD-20)"],
    ["Questions (answer lines) presented", f"{n_answer_lines} (OD-01: 4; OD-17: 2; OD-19: 3; every other decision: 1; OD-21's line is blocked)"],
    ["Release-blocking decisions", f"{len(blocking)} ({', '.join(blocking)})"],
    ["Non-release-blocking decisions", f"{len(nonblocking)} ({', '.join(nonblocking)})"],
    ["Decisions answered (recorded 2026-10-06)", f"{len(SUMMARY) - 1} (OD-01 \u2013 OD-20); {len(CHOSEN)} of {n_answer_lines} answer lines marked"],
    ["Decisions still pending", f"1 ({SIGNOFF} release sign-off: BLOCKED \u2014 owner's position \u201cNOT APPROVED YET \u2014 PREREQUISITES NOT COMPLETE\u201d; not signed)"],
], widths_cm=[7.0, 9.5])
page_break()

# --------------------------------------------------------------------------------------------
# Appendix A — traceability
# --------------------------------------------------------------------------------------------
h("Appendix A — Traceability matrix", 1)
para(f"Every owner-decision box, located by its exact text (line at HEAD {HEAD} and in today's working tree), and the "
     "decision that covers it. Each box maps to exactly one decision. Supporting rules OD-11 \u2013 OD-20 have no box; "
     "they are traced to the Human Review Package references in decision group 9.")
table(["Line (HEAD / today)", "Exact box text", "Stage", "Role", "Decision"],
      [[line_ref(ln, label), label.replace("**", ""), st, role, od] for ln, label, od, st, role in BOXES],
      widths_cm=[2.4, 6.0, 1.1, 3.8, 3.2], font_size=8)

# --------------------------------------------------------------------------------------------
# Appendix B — deferred issues
# --------------------------------------------------------------------------------------------
h("Appendix B — The 30 deferred (post-launch) issues for OD-02", 1)
para("Source: docs/issues-and-bugs/triage-register.md (classification “Post-launch (proposed)”, all Medium). "
     "Status: Stage 9 re-run (docs/testing/stage-09-qa-rerun-results.md, 2026-09-27) with later changes noted. "
     "**Use the ACCEPT / REJECT boxes only if you chose OD-02 option B.**")
table(["#", "ID", "Issue", "Area", "Task", "Status / evidence", "Owner (only if OD-02 = B)"],
      [[str(i), d[0], d[1], d[2], d[3], d[4], f"{BOX} ACCEPT  {BOX} REJECT"] for i, d in enumerate(DEFERRED, 1)],
      widths_cm=[0.7, 1.8, 3.6, 1.8, 1.2, 4.6, 2.8], font_size=7.5)

h("Appendix C — Evidence references", 1)
for ref in [
    "docs/NarratIQ_Master_Implementation_Checklist.md (HEAD " + HEAD + ")",
    "docs/releases/v3.3.0-sign-off.md (§1 gates, §3 accepted issues, §4 waivers, §7 rollback, §9 blockers, §10 sign-off)",
    "docs/testing/stage-12/stage-12.1/owner-decisions.md; stage-12.1-final-decision-package.md (A4, F)",
    "docs/testing/stage-12/stage-12.1/gate4-section3-review.md (G5; CAST-H10 accepted)",
    "docs/testing/stage-12/stage-12.1/gate3b-review/README.md §4; human-review-decisions.md (A1, A2)",
    "docs/testing/stage-12/tranche3/mv-5.14-a.json, mv-5.14-a-before-fix.json, mv-5.14-b.json, mv-5.14-c.json and screenshots",
    "docs/testing/manual-verification/stage-05-manual-verification-guide.md (MV-5.14-A–D)",
    "docs/issues-and-bugs/triage-register.md; docs/testing/stage-09-qa-rerun-results.md",
    "docs/operations/capacity-planning.md; docs/testing/performance-baselines.md §6",
    "docs/testing/manual-verification/stage-10-manual-verification-guide.md (MV-10.8)",
    "scripts/startup_backup.sh; docs/operations/backup-and-restore.md §4a",
    "docs/testing/stage-12/stage-12.1/awt-g-consistency.md",
]:
    bullet(ref)

doc.save(OUT)


# --------------------------------------------------------------------------------------------
# Validation (re-open the produced file)
# --------------------------------------------------------------------------------------------
def validate() -> list[str]:
    errors: list[str] = []
    head_text = subprocess.run(["git", "-C", str(REPO), "show", f"{HEAD}:{CHECKLIST}"],
                               capture_output=True, text=True, check=True).stdout.splitlines()
    work_lines = (REPO / CHECKLIST).read_text(encoding="utf-8").splitlines()
    is_box = re.compile(r"^\s*- \[[ x]\]")
    is_open = re.compile(r"^\s*- \[ \]")

    # 1. Each box: exact text at its HEAD line (where it existed at HEAD); located by TEXT in the working tree,
    #    exactly once; open unless it is the closed L3531.
    print("Box verification (HEAD", HEAD, "and working tree, located by text)")
    for ln, label, od, _st, _role in BOXES:
        if ln is not None:
            line = head_text[ln - 1]
            if label not in line or not is_open.match(line):
                errors.append(f"L{ln}: quoted text not an open box at HEAD")
        cur = [i + 1 for i, l in enumerate(work_lines) if label in l and is_box.match(l)]
        if len(cur) != 1:
            errors.append(f"{label[:50]}: found {len(cur)} times in the working tree")
            continue
        open_now = bool(is_open.match(work_lines[cur[0] - 1]))
        if od in CLOSED_BOXES and open_now:
            errors.append(f"{label[:50]}: expected ticked (already decided) but open")
        # Since the owner's answers of 2026-10-06 a box may be ticked once its decision is recorded
        # (OD-01 – OD-10). The sign-off boxes (OD-21) must always stay open.
        decided = {k.split(" ")[0] for k in ANSWERS} - {SIGNOFF}
        if od not in CLOSED_BOXES and not open_now and od not in decided:
            errors.append(f"{label[:50]}: expected open but ticked")
        print(f"  HEAD {str(ln):>4} / today L{cur[0]:>4} {'open' if open_now else 'TICKED':6} -> {od}")
        BOX_STATE[label] = open_now

    # 2. Every box maps to exactly one decision; box decisions have >= 1 box; supporting decisions have none.
    labels = [b[1] for b in BOXES]
    if len(set(labels)) != len(labels):
        errors.append("a box is listed twice")
    for _ln, label, od, *_ in BOXES:
        if od not in DECISION_IDS and od not in CLOSED_BOXES:
            errors.append(f"{label[:40]} maps to unknown decision {od}")
    for od in BOX_DECISIONS:
        if not any(b[2] == od for b in BOXES):
            errors.append(f"{od} has no checklist box")
    for od in SUPPORTING:
        if any(b[2] == od for b in BOXES):
            errors.append(f"supporting {od} unexpectedly has a box")
    n_open_boxes = len([b for b in BOXES if b[2] not in CLOSED_BOXES])
    if len(BOXES) != 22 or n_open_boxes != 21:
        errors.append(f"box counts are {len(BOXES)} / {n_open_boxes}, expected 22 / 21")

    d = Document(OUT)
    paras = [p.text for p in d.paragraphs]
    cell_texts = [c.text for t in d.tables for r in t.rows for c in r.cells]
    full = "\n".join(paras + cell_texts)

    # 3. Answers: exactly the owner's recorded choices, nothing else; OD-21 unanswered.
    for ch in ("☑", "✓", "✔", "✗", "✘", "[x]", "[X]"):
        if ch in full:
            errors.append(f"filled-answer glyph {ch!r} present")
    summary = d.tables[0]
    hdr = [c.text for c in summary.rows[0].cells]
    if "Owner Answer" not in hdr:
        errors.append("summary table not first / missing Owner Answer column")
    else:
        idx = hdr.index("Owner Answer")
        st = hdr.index("Status")
        for r in summary.rows[1:]:
            od = r.cells[0].text
            if r.cells[idx].text != SUMMARY_ANSWERS.get(od):
                errors.append(f"summary Owner Answer for {od} does not match the recorded answer")
            want = "BLOCKED — PREREQUISITES NOT COMPLETE" if od == SIGNOFF else "ANSWERED"
            if r.cells[st].text != want:
                errors.append(f"summary Status for {od} is {r.cells[st].text!r}")
        ids = [r.cells[0].text for r in summary.rows[1:]]
        if ids != DECISION_IDS:
            errors.append(f"summary IDs {ids}")
    answer_paras = [p for p in paras if p.startswith("OWNER ANSWER")]
    if len(answer_paras) != len(ANSWER_LINES):
        errors.append(f"expected {len(ANSWER_LINES)} answer lines, found {len(answer_paras)}")
    if len(CHOSEN) != len(ANSWERS):
        errors.append(f"{len(CHOSEN)} answers marked, {len(ANSWERS)} recorded")
    for p in answer_paras:
        label, after = p.split(":", 1)
        if SIGNOFF in label:
            if BOX_X in after or after.count(BOX) != 2:
                errors.append("OD-21 has a marked box (must stay unsigned)")
            continue
        if after.count(BOX_X) != 1:
            errors.append(f"answer line without exactly one recorded choice: {p[:60]}")
        elif f"{BOX_X} {CHOSEN.get(label, '?')}" not in after:
            errors.append(f"marked option differs from the recorded answer: {p[:60]}")
    for od in DECISION_IDS:
        if not any(od in p for p in answer_paras):
            errors.append(f"{od} has no OWNER ANSWER line")
    notes = [p for p in paras if p.startswith("OWNER NOTES (optional):")]
    for p in notes:
        body = p.replace("OWNER NOTES (optional):", "").strip()
        if body not in OWNER_NOTES.values():
            errors.append(f"owner notes not the recorded text: {body[:50]}")
    if sum(p == RECORDED_LINE for p in paras) != len(DECISION_IDS):
        errors.append("transcription line missing on a decision")
    if OD21_POSITION not in full:
        errors.append("OD-21 owner position missing")
    so = paras.index("FINAL RELEASE SIGN-OFF — DO NOT COMPLETE YET") if "FINAL RELEASE SIGN-OFF — DO NOT COMPLETE YET" in paras else 0
    sig = [p for p in paras[so:] if re.match(r"^(Release commit|Conditions \(if any\)|Name|Role|Date \(UTC\)|Written approval \(verbatim\)):", p)]
    if len(sig) != 6 or any(x.split(":", 1)[1].strip().strip("_") for x in sig):
        errors.append("OD-21 signature fields not blank")
    if len(notes) != len(DECISION_IDS) - 1:
        errors.append(f"expected {len(DECISION_IDS) - 1} OWNER NOTES lines, found {len(notes)}")
    for od in DECISION_IDS:
        if not any(p.startswith(f"{od} —") for p in paras):
            errors.append(f"{od} heading missing")
    if sum(p.startswith("TECHNICAL RECOMMENDATION:") for p in paras) != len(DECISION_IDS) - 1:
        errors.append("expected a TECHNICAL RECOMMENDATION for every decision except the sign-off")
    if sum(p.startswith("WHY:") for p in paras) != len(DECISION_IDS) - 1:
        errors.append("expected a WHY for every decision except the sign-off")
    # every Human Review Package OWNER THRESHOLD reference group is answered
    for ref in ("(G3)", "(G1)", "(G1 / A15 thresholds)", "(A3)", "(G5)", "(G6)", "(G7)", "(G8)", "(A6)",
                "(A6 / 7.12)", "(A6 / 5.10)", "(11.7)"):
        if ref not in full:
            errors.append(f"Human Review Package reference {ref} not answered")

    # 4. Sign-off section separated and BLOCKED, after all other decisions, preceded by a page break.
    title = "FINAL RELEASE SIGN-OFF — DO NOT COMPLETE YET"
    pos = [i for i, p in enumerate(d.paragraphs) if p.text == title and p.style.name == "Heading 1"]
    if len(pos) != 1:
        errors.append("sign-off Heading 1 missing or duplicated")
    else:
        i = pos[0]
        if "STATUS: BLOCKED UNTIL RELEASE PREREQUISITES PASS" not in d.paragraphs[i + 1].text:
            errors.append("sign-off BLOCKED status line missing")
        if 'w:type="page"' not in d.paragraphs[i - 1]._p.xml:
            errors.append("no page break before sign-off section")
        others = [j for j, p in enumerate(d.paragraphs)
                  if any(p.text.startswith(f"{od} —") for od in DECISION_IDS if od != SIGNOFF)]
        if max(others) > i:
            errors.append("sign-off section not after the other decisions")
        heads = [j for j, p in enumerate(d.paragraphs) if p.text.startswith(f"{SIGNOFF} —")]
        comp = [j for j, p in enumerate(d.paragraphs) if p.text == "OWNER DECISION COMPLETION SUMMARY"]
        if not heads or not comp or not (i < heads[0] < comp[0]):
            errors.append(f"{SIGNOFF} not inside the sign-off section")
        for j, p in enumerate(d.paragraphs):
            if p.text.startswith("OWNER ANSWER") and SIGNOFF in p.text and not (i < j < comp[0]):
                errors.append("sign-off answer outside sign-off section")
            if p.text.startswith("OWNER ANSWER") and SIGNOFF not in p.text and j > i:
                errors.append("another decision's answer inside the sign-off section")
    if "BLOCKED — PREREQUISITES NOT COMPLETE" not in full:
        errors.append("summary BLOCKED status missing")

    # 5. Header, footer PAGE field, TOC field.
    sec_ = d.sections[0]
    if HEADER_TEXT not in sec_.header.paragraphs[0].text:
        errors.append("header text missing")
    if "PAGE" not in sec_.footer._element.xml:
        errors.append("footer PAGE field missing")
    if "TOC \\o" not in d.element.body.xml:
        errors.append("TOC field missing")

    # 6. Traceability: every box present once with its decision.
    trace = [t for t in d.tables if t.rows[0].cells[0].text.startswith("Line (HEAD")]
    if len(trace) != 1:
        errors.append("traceability table missing")
    else:
        rows = sorted((r.cells[1].text, r.cells[-1].text) for r in trace[0].rows[1:])
        if rows != sorted((b[1].replace("**", ""), b[2]) for b in BOXES):
            errors.append("traceability rows do not match BOXES")
        if any("not found" in r.cells[0].text for r in trace[0].rows[1:]):
            errors.append("traceability has a box not found in the working tree")

    # 7. Deferred appendix has 30 rows.
    dtab = [t for t in d.tables if t.rows[0].cells[1].text == "ID" and "Owner (only if OD-02 = B)" in t.rows[0].cells[-1].text]
    if len(dtab) != 1 or len(dtab[0].rows) != 31:
        errors.append("deferred-issues appendix is not 30 rows")

    # 8. No secrets.
    if re.search(r"(SECRET_KEY\s*=\s*\S|password\s*[:=]\s*\S|PGPASSWORD=\S|eyJ[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{20,})",
                 full, re.I):
        errors.append("possible secret in document")
    return errors


if __name__ == "__main__":
    errs = validate()
    print(f"Wrote {OUT}")
    print(f"Answer lines: {len(ANSWER_LINES)}; gate result lines: {GATE_RESULT_LINES}")
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    n_now_open = sum(BOX_STATE.values())
    print(f"Checklist state now: {n_now_open} of 22 boxes open, {22 - n_now_open} ticked (decided boxes may be ticked; OD-21 stays open).")
    print("VALIDATION PASSED: 22 boxes (21 decision boxes + L3531 already decided) located by text and mapped to exactly one decision "
          "each; 10 supporting rules without boxes; 26 owner answers recorded exactly as given (one choice per line, "
          "notes + transcription line on OD-01 - OD-20); OD-21 unmarked and unsigned; sign-off section separated and BLOCKED; "
          "header, PAGE and TOC fields present; 30 deferred issues listed; every OWNER THRESHOLD reference answered; "
          "no secrets.")
