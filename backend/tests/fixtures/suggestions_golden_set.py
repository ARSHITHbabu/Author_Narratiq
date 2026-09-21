"""
Stage 5 task 5.13 — golden set for measuring AI-suggestions quality.

5 short synthetic passages, each engineered around ONE clearly-nameable
craft weakness. `expected_keywords` is a deterministic, objective proxy for
"did the suggestions actually detect THIS weakness" — at least one
suggestion's observation+recommendation text containing one of these
keywords is evidence of detection, not proof (a human could still write a
suggestion about the same weakness using none of these exact words) — same
proxy-metric discipline as transform_golden_set.py's own metrics.
"""

PASSAGES = [
    {
        "id": "repetitive-structure",
        "weakness": "repetitive sentence structure / monotonous rhythm",
        "text": (
            "She walked into the room. She saw the note on the table. She picked it up. "
            "She read it twice. She put it down. She walked back out."
        ),
        "expected_keywords": ["repetit", "monoton", "vary", "structure", "rhythm", "sentence", "combine", "concise", "choppy"],
    },
    {
        "id": "telling-not-showing",
        "weakness": "telling emotion directly instead of showing it",
        "text": (
            "Maria was furious. She was also very sad about what had happened. "
            "She felt betrayed and did not know what to do next."
        ),
        "expected_keywords": ["show", "tell", "state", "emotion", "interiority", "sensory"],
    },
    {
        "id": "generic-dialogue",
        "weakness": "flat, generic dialogue with no character voice",
        "text": (
            '"Hello," she said. "How are you?" he said. '
            '"I am fine," she said. "That is good," he said.'
        ),
        "expected_keywords": ["dialogue", "voice", "generic", "flat", "distinct", "tag"],
    },
    {
        "id": "info-dump",
        "weakness": "exposition dumped directly rather than woven in",
        "text": (
            "The kingdom of Everholt had been founded three hundred years ago by King "
            "Aldric the First, who established the Council of Nine, a body that still "
            "governed trade, taxation, and military matters according to the founding "
            "charter written in the old tongue."
        ),
        "expected_keywords": ["info", "dump", "exposition", "expository", "weave", "backstory", "scene"],
    },
    {
        "id": "flat-description",
        "weakness": "vague adjectives with no sensory specificity",
        "text": (
            "It was a nice, big house with a nice garden. The rooms were nice and "
            "spacious, and the view was very nice too."
        ),
        "expected_keywords": ["vague", "generic", "specific", "sensory", "concrete", "detail"],
    },
]
