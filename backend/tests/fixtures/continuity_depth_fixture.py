"""
Stage 5 task 5.14 — controlled fixtures for measuring whether the deepened
check_continuity prompt (motivation/relationship contradiction types +
character_arc_notes/relationship_changes wired into the prompt) actually
catches contradictions the ORIGINAL prompt structurally could not detect
(it only asked about character_appearance/character_location/world_rule/
timeline, and never saw arc/relationship data at all).

Each scenario is a minimal, synthetic 2-chapter manuscript with EXACTLY one
deliberate problem (or, for the control cases, none) — small enough that a
recall/false-positive check can be read by eye, not just by the model.
"""

CHARACTER_PROFILES = [
    {"name": "Kael", "appearance": "scarred left hand", "status": "alive", "goals": "protect his sister"},
]

# 1. Motivation contradiction — no surface fact clashes at all (same name,
# same location type, same rough timeline); the ONLY problem is that
# chapter 2's action is irreconcilable with chapter 1's established, stated
# motivation. The ORIGINAL prompt never asked about motivation, so this is
# exactly the class of problem it was structurally blind to.
MOTIVATION_CASE = {
    "chapter_summaries": [
        {"chapter_number": 1, "locations": ["the harbor"], "characters_present": ["Kael"],
         "key_events": ["Kael swears he will never raise a weapon against his own sister"],
         "character_arc_notes": {"kael": "Kael swears he will never raise a weapon against his own sister"},
         "relationship_changes": []},
        {"chapter_number": 2, "locations": ["the harbor"], "characters_present": ["Kael"],
         "key_events": ["Kael draws his sword on his sister without hesitation"],
         "character_arc_notes": {}, "relationship_changes": []},
    ],
    "expected_type_keywords": ["motivation"],
}

# 2. Relationship contradiction — a stated reconciliation directly followed
# by the same two characters acting as if the rift never happened, with
# nothing else surface-inconsistent.
RELATIONSHIP_CASE = {
    "chapter_summaries": [
        {"chapter_number": 1, "locations": ["the manor"], "characters_present": ["Kael", "Priya"],
         "key_events": ["Kael and Priya reconcile after years of estrangement"],
         "character_arc_notes": {},
         "relationship_changes": [{"characters": ["Kael", "Priya"], "change": "they reconcile fully"}]},
        {"chapter_number": 2, "locations": ["the manor"], "characters_present": ["Kael", "Priya"],
         "key_events": ["Priya refuses to speak to Kael, still estranged"],
         "character_arc_notes": {}, "relationship_changes": []},
    ],
    "expected_type_keywords": ["relationship"],
}

# 3. Control — a genuine SURFACE contradiction (character_location), the
# class the original prompt was already built to catch. This checks the
# deepened prompt didn't LOSE recall on the original categories while
# gaining the new ones.
SURFACE_CONTROL_CASE = {
    "chapter_summaries": [
        {"chapter_number": 1, "locations": ["Paris"], "characters_present": ["Kael"],
         "key_events": ["Kael arrives in Paris"], "character_arc_notes": {}, "relationship_changes": []},
        {"chapter_number": 2, "locations": ["Tokyo"], "characters_present": ["Kael"],
         "key_events": ["Kael has breakfast in Tokyo, having never left Paris"],
         "character_arc_notes": {}, "relationship_changes": []},
    ],
    "expected_type_keywords": ["location", "timeline"],
}

# 4. Control — genuinely clean, no contradiction of any kind. Checks the
# deepened prompt didn't raise the false-positive rate.
CLEAN_CONTROL_CASE = {
    "chapter_summaries": [
        {"chapter_number": 1, "locations": ["the harbor"], "characters_present": ["Kael"],
         "key_events": ["Kael boards the ship"], "character_arc_notes": {}, "relationship_changes": []},
        {"chapter_number": 2, "locations": ["the ship"], "characters_present": ["Kael"],
         "key_events": ["Kael settles into his cabin"], "character_arc_notes": {}, "relationship_changes": []},
    ],
    "expected_type_keywords": [],
}
