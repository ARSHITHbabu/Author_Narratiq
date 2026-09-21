"""
A second, structurally different synthetic manuscript for Stage 4 task 4.16's
generalizability requirement: a fix proven on only one manuscript (and one
genre/register) risks being tuned to that manuscript's phrasing rather than a
real, general improvement. This one is deliberately different from
retrieval_fixture.py's fantasy-mystery register — near-future, technical,
present-tense-adjacent register, single POV character, no mystery structure.

Small on purpose (2 chapters) — only large enough to exercise the specific
character-bible behaviour under test (physical-description grounding), not a
second full retrieval fixture.
"""

CHAPTERS: list[dict] = [
    {
        "number": 1,
        "title": "Calibration",
        "content": (
            "<p>Priya Nathan adjusted the sensor array for the third time that "
            "shift, the cold of the server room seeping through her lab coat. "
            "She had inherited the anomaly detection project from a researcher "
            "who quit without documentation, and the readings made no sense: "
            "a signal repeating every 6.2 hours, far too regular to be noise.</p>"
            "<p>Her supervisor, Dr. Okafor, dismissed it as a hardware fault "
            "without looking at the data twice. Priya kept the printout anyway, "
            "folded into her badge lanyard, and ran the calibration again after "
            "everyone else had gone home.</p>"
        ),
    },
    {
        "number": 2,
        "title": "The Pattern",
        "content": (
            "<p>By midnight, Priya had mapped eleven repetitions of the signal "
            "and one clear deviation: on the ninth cycle, the interval had "
            "shortened by four minutes, then corrected itself on the tenth. "
            "That was not hardware drift. That was something adjusting.</p>"
            "<p>She sent the corrected dataset to Dr. Okafor with a single "
            "line: 'This is not noise.' He did not reply that night, but the "
            "sensor array was reassigned to a restricted project the following "
            "morning, and Priya's access badge stopped working at the lab door.</p>"
        ),
    },
]
