"""
Stage 5 task 5.2 — golden set for transform-quality measurement.

12 short synthetic passages across 3 structurally distinct genres/registers,
each tagged with which scenarios it's meaningful for. Deliberately small —
this exists to catch regressions and demonstrate before/after evidence, not
to be statistically exhaustive (same scoping principle as Stage 4's 6-chapter
retrieval fixture).

Metric naming (per the approved correction to task 5.2): the measurements
below are DETERMINISTIC, OBJECTIVE proxies, not direct measurements of
subjective qualities:
  - SequenceMatcher ratio is TEXTUAL/EDIT SIMILARITY (or "preservation /
    edit-distance evidence") — never described as measuring "authorial voice"
    directly. Voice is a human judgment, supported but not replaced by this.
  - BGE-M3 cosine similarity (original vs. transformed embedding) is
    SEMANTIC/CONTENT PRESERVATION SIMILARITY — never described as measuring
    "genre drift" directly, since nothing here independently measures genre
    as a category.
Both are raw, reproducible numbers recorded alongside the final report so a
reader can tell deterministic evidence apart from the blind author review
required to close the Stage 5 gate's subjective criteria.
"""

PASSAGES: list[dict] = [
    # ── Genre A: gothic/literary, restrained, distinctive voice ────────────
    {
        "id": "gothic-1",
        "genre": "gothic literary",
        "text": (
            "The house had not been opened in eleven years, and the air inside "
            "kept the shape of that absence — still, cold, faintly sweet with "
            "dust. Mira did not call out. There was no one left to answer."
        ),
        "tags": ["distinctive_voice", "restrained_emotion"],
    },
    {
        "id": "gothic-2",
        "genre": "gothic literary",
        "text": (
            "She had learned, over the years, to say nothing when she was most "
            "afraid. The habit had outlived its reason. Even now, alone in the "
            "hall, she found herself arranging her face into something calm."
        ),
        "tags": ["distinctive_voice", "restrained_emotion", "already_suitable_adult"],
    },
    {
        "id": "gothic-3",
        "genre": "gothic literary",
        "text": (
            "The letter had said everything and nothing. Devika read it twice, "
            "then folded it back along its old creases, as if that alone could "
            "undo the reading."
        ),
        "tags": ["distinctive_voice", "lock_scenario"],
        "lock_target": "Devika read it twice",
    },
    {
        "id": "gothic-4",
        "genre": "gothic literary",
        "text": (
            "He kept the key on a chain he never removed, not because he "
            "expected to need it again, but because a man who has once locked "
            "a door does not easily trust himself to leave it unlocked."
        ),
        "tags": ["distinctive_voice", "already_suitable_ya"],
    },
    # ── Genre B: technical/near-future, plain register ──────────────────────
    {
        "id": "tech-1",
        "genre": "near-future technical",
        "text": (
            "The sensor array logged a spike at 03:14, four minutes early "
            "relative to the established cycle. Priya flagged the anomaly and "
            "ran the calibration a second time. The result did not change."
        ),
        "tags": ["plain_register"],
    },
    {
        "id": "tech-2",
        "genre": "near-future technical",
        "text": (
            "Access to the lab required two separate badge scans and a "
            "supervisor override after 22:00. Priya had never used the "
            "override before tonight."
        ),
        "tags": ["plain_register", "lock_scenario"],
        "lock_target": "Priya had never used the override before tonight",
    },
    {
        "id": "tech-3",
        "genre": "near-future technical",
        "text": (
            "The report was three pages, all of it technically accurate and "
            "none of it honest about what the numbers actually implied."
        ),
        "tags": ["plain_register", "already_suitable_adult"],
    },
    {
        "id": "tech-4",
        "genre": "near-future technical",
        "text": (
            "By morning the anomaly had a name, a case number, and a team of "
            "four people who had not been told what they were actually "
            "looking for."
        ),
        "tags": ["plain_register"],
    },
    # ── Genre C: adventure/action, energetic register ───────────────────────
    {
        "id": "adventure-1",
        "genre": "adventure",
        "text": (
            "The bridge gave way behind them with a sound like a held breath "
            "finally let go. Kael did not look back. There was nothing behind "
            "them worth the half-second it would cost."
        ),
        "tags": ["high_energy"],
    },
    {
        "id": "adventure-2",
        "genre": "adventure",
        "text": (
            "Three arrows, three misses, and the fourth still in her quiver — "
            "Aanya was not going to get a fifth chance, and she knew it."
        ),
        "tags": ["high_energy", "lock_scenario"],
        "lock_target": "Aanya was not going to get a fifth chance",
    },
    {
        "id": "adventure-3",
        "genre": "adventure",
        "text": (
            "The children's version of the story left out the part where "
            "nobody survived the first crossing. This was, Mira thought, "
            "probably for the best."
        ),
        "tags": ["high_energy", "already_suitable_children_needs_check"],
    },
    {
        "id": "adventure-4",
        "genre": "adventure",
        "text": (
            "The old guide had warned them about the pass, the weather, and "
            "the wolves, in that order, as if the order mattered."
        ),
        "tags": ["high_energy"],
    },
]

# passage-id -> which transform each is a meaningful pre-existing "already
# suitable" test for (used by task 5.5's no-change assertions)
ALREADY_SUITABLE_FOR = {
    "gothic-2": ("age_adapt", "adult"),
    "gothic-4": ("age_adapt", "ya"),
    "tech-3": ("age_adapt", "adult"),
}

LOCK_SCENARIOS = {p["id"]: p["lock_target"] for p in PASSAGES if "lock_scenario" in p["tags"]}
