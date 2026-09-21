"""
Stage 5 task 5.12-H — "different authors must not converge on one voice."

Two synthetic passages describing roughly the SAME underlying scenario (arriving
at a locked door in the rain) but written in two deliberately distinct voices —
so a meaningful convergence test is possible: any similarity between the two
OUTPUTS beyond their similarity as ORIGINALS is evidence of the transform
flattening distinct voices toward each other, not evidence of them naturally
overlapping because they described different things.

VOICE_A: terse, minimalist, short declarative sentences.
VOICE_B: florid, lyrical, long subordinate clauses.
"""

VOICE_A = {
    "id": "voice-a-terse",
    "text": (
        "Rain fell. Mara walked. The street was empty. She reached the door. "
        "It was locked. She knocked twice. No one answered."
    ),
}

VOICE_B = {
    "id": "voice-b-lyrical",
    "text": (
        "The rain came down in long silver threads, and Mara moved through it "
        "unhurried, as though the storm itself were waiting for her; when at "
        "last she reached the door and found it locked, she knocked — twice, "
        "softly, like a question she already suspected would go unanswered."
    ),
}
