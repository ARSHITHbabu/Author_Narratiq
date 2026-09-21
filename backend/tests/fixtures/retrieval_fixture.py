"""
Shared multi-chapter fixture manuscript with documented ground truth.

Built once for Stage 4 task 4.2 (recall measurement) and reused by 4.15
(retrieval regression suite) so the two tasks don't duplicate fixture-building
work, per the approved Stage 4 plan.

6 chapters, each with 2-3 ground-truth facts that are specific enough to be
found (or missed) by retrieval unambiguously. GROUND_TRUTH maps each fact to
the chapter it lives in and a query that should retrieve it. Chapters are
deliberately structurally different from each other (different settings,
character sets, register) so a fix tuned to one chapter's phrasing style
doesn't quietly become the only thing that works.

This is entirely synthetic content — no relation to any real manuscript.
"""

CHAPTERS: list[dict] = [
    {
        "number": 1,
        "title": "The Salt Road",
        "content": (
            "<p>Mira Okoye had walked the salt road for three days before the "
            "watchtower of Greyharn finally rose over the dunes. Her boots were "
            "worn through at the heel, and the waterskin at her side had gone "
            "dry since dawn. She carried a single object wrapped in oilcloth: "
            "a bronze compass that did not point north, but toward whatever the "
            "holder most wanted to find.</p>"
            "<p>The gate warden, a heavyset man named Corvin Ashe, stopped her "
            "at the threshold. He recognized the oilcloth bundle immediately "
            "and paled. 'That belonged to the Cartographer,' he said. 'She died "
            "here eleven years ago, in the flood that took the lower quarter.' "
            "Mira said nothing. She had not come to explain herself to a gate "
            "warden.</p>"
            "<p>Inside the walls, Greyharn smelled of tar and brine. Mira found "
            "the address she had been given — a narrow shop on Coopers Row run "
            "by an old woman called Hessa Lin, who traded exclusively in maps "
            "that no longer matched the land they described.</p>"
        ),
    },
    {
        "number": 2,
        "title": "Coopers Row",
        "content": (
            "<p>Hessa Lin did not look up when Mira entered. 'You're the one "
            "with the compass,' she said, still bent over a table covered in "
            "yellowed vellum. 'I heard you'd be three days later than this.' "
            "Hessa's shop held maps of coastlines that had eroded away decades "
            "ago and cities renamed twice since they were drawn.</p>"
            "<p>Hessa explained that the compass would only work once, and only "
            "at the Hollow Cistern beneath the old temple district — a place "
            "sealed since the flood of eleven years past. To reach it, Mira "
            "would need the seven-toothed key that Corvin Ashe, the gate "
            "warden, kept hidden in the watchtower's lower archive, though he "
            "would never admit to having it.</p>"
            "<p>'Why are you helping me?' Mira finally asked. Hessa set down her "
            "pen. 'Because the Cartographer was my sister,' she said, 'and I "
            "want to know why she really drowned.'</p>"
        ),
    },
    {
        "number": 3,
        "title": "The Lower Archive",
        "content": (
            "<p>Corvin Ashe kept the watchtower's lower archive locked with "
            "three separate mechanisms, each one older than the last. When "
            "Mira confronted him about the seven-toothed key, he did not deny "
            "having it — he simply asked how she knew about the Hollow "
            "Cistern at all, since its location had been struck from every "
            "surviving map after the flood.</p>"
            "<p>Reluctantly, Corvin handed over the key, but warned her that "
            "the Cistern had not been opened since the disaster because "
            "something inside it — he would not say what — had been heard "
            "moving in the years since. He made her promise that if she found "
            "the Cartographer's notebook down there, she would bring it "
            "straight to him and no one else.</p>"
            "<p>Mira agreed, though she had already decided she would not keep "
            "that promise if the notebook explained what she suspected: that "
            "the flood eleven years ago had not been an accident at all.</p>"
        ),
    },
    {
        "number": 4,
        "title": "The Hollow Cistern",
        "content": (
            "<p>The Cistern's outer door had rusted shut, and Mira spent an "
            "hour working the seven-toothed key before the ancient lock gave "
            "way. Inside, the air was cold and smelled of standing water long "
            "gone stagnant and dried. Bronze fittings on the walls still held "
            "the shape of a compass rose, matching the one wrapped in her "
            "oilcloth bundle exactly.</p>"
            "<p>At the center of the chamber, half-submerged in dried silt, "
            "Mira found the Cartographer's notebook, its pages swollen but "
            "legible. The final entry, dated the night of the flood, named "
            "the person who had ordered the lower quarter's floodgates sealed "
            "from the inside: Magistrate Ondrej Vell, Greyharn's harbor "
            "official, who had drowned three hundred people to hide a "
            "smuggling ledger he could not afford to have found.</p>"
            "<p>Mira heard something shift in the darkness behind the far "
            "wall — slow, deliberate, and much larger than a rat.</p>"
        ),
    },
    {
        "number": 5,
        "title": "What Moved in the Dark",
        "content": (
            "<p>The thing that emerged from behind the Cistern's far wall was "
            "not a creature at all, but Magistrate Ondrej Vell himself — alive, "
            "gaunt, and hiding in the one place no one had thought to search "
            "for eleven years, having faked his own death in the very flood he "
            "caused. He had been surviving on stores smuggled down by a single "
            "loyal harbor guard.</p>"
            "<p>Vell begged Mira for the notebook, offering her gold, passage "
            "out of Greyharn, anything. When she refused, he admitted the "
            "smuggling ledger had recorded weapons shipments to a rival city, "
            "Tharsk, which would have started a war he alone had the power to "
            "prevent — or so he claimed, twisting the truth to excuse three "
            "hundred deaths.</p>"
            "<p>Mira did not believe him. She took the notebook and left him "
            "in the dark, exactly as he had left the lower quarter eleven "
            "years before.</p>"
        ),
    },
    {
        "number": 6,
        "title": "Coopers Row, Again",
        "content": (
            "<p>Hessa Lin read her sister's final notebook entry twice before "
            "she spoke. 'Ondrej Vell,' she said quietly, 'is still the "
            "harbor magistrate. He never left office.' Mira confirmed what "
            "Hessa already suspected — that Vell was alive, hidden beneath "
            "the very city he had flooded to protect himself.</p>"
            "<p>Corvin Ashe, when told, refused at first to believe a "
            "magistrate could have sealed the floodgates himself, until Hessa "
            "showed him the notebook's final page. He agreed to bring the "
            "notebook before Greyharn's council the next morning, though he "
            "warned that Vell still had allies among the harbor guard who "
            "would not let the truth surface quietly.</p>"
            "<p>Mira set the bronze compass on Hessa's table. It had done what "
            "she most wanted — led her to the truth about the Cartographer's "
            "death — and now pointed at nothing at all.</p>"
        ),
    },
]

# Each entry: (query, expected_chapter, fact_description)
# The query is phrased naturally, as an author might ask it; expected_chapter
# is the ONE chapter that contains the grounding evidence for that fact.
GROUND_TRUTH: list[dict] = [
    {"query": "What object did Mira carry wrapped in oilcloth?",
     "chapter": 1, "fact": "a bronze compass that points to what the holder wants"},
    {"query": "Who is the gate warden of Greyharn?",
     "chapter": 1, "fact": "Corvin Ashe"},
    {"query": "What kind of maps does Hessa Lin sell?",
     "chapter": 2, "fact": "maps of places that no longer match the land they describe"},
    {"query": "Why is Hessa Lin helping Mira?",
     "chapter": 2, "fact": "the Cartographer was Hessa's sister"},
    {"query": "What does Mira need to reach the Hollow Cistern?",
     "chapter": 2, "fact": "the seven-toothed key"},
    {"query": "What promise does Corvin ask Mira to make about the notebook?",
     "chapter": 3, "fact": "bring the Cartographer's notebook straight to him"},
    {"query": "What did Mira find at the center of the Hollow Cistern?",
     "chapter": 4, "fact": "the Cartographer's notebook, swollen but legible"},
    {"query": "Who ordered the floodgates sealed during the flood?",
     "chapter": 4, "fact": "Magistrate Ondrej Vell"},
    {"query": "Who was hiding behind the far wall of the Hollow Cistern?",
     "chapter": 5, "fact": "Magistrate Ondrej Vell, alive"},
    {"query": "What excuse does Vell give for causing the flood?",
     "chapter": 5, "fact": "hiding a smuggling ledger about weapons shipments to Tharsk"},
    {"query": "What does Corvin agree to do with the notebook?",
     "chapter": 6, "fact": "bring it before Greyharn's council"},
    # A LATE fact — only reachable under full-manuscript scope from chapter 1,
    # deliberately reused by the 4.1 scope tests' spirit but scoped here for 4.2.
    {"query": "Is Ondrej Vell still the harbor magistrate?",
     "chapter": 6, "fact": "yes — he never left office"},
]


async def build_fixture(db):
    """
    Insert the fixture manuscript (user, story, chapters, embedded chunks).
    Returns {"user_id", "story_id", "chapter_ids": {number: id}}.
    Caller is responsible for cleanup (delete story + user via ORM cascade).
    """
    import uuid
    from models import User, Story, Chapter
    from services.ai_service import embed_and_store_chunks
    from routers.search import _html_to_plain

    tag = uuid.uuid4().hex[:8]
    user = User(
        email=f"retrieval-fixture-{tag}@narratiq-internal-test.com",
        username=f"retrievalfixture{tag}",
        hashed_password="x",
    )
    db.add(user)
    db.flush()

    story = Story(user_id=user.user_id, title=f"[4.2/4.15-FIXTURE] The Salt Road ({tag})")
    db.add(story)
    db.flush()

    chapter_ids: dict[int, str] = {}
    for ch_def in CHAPTERS:
        ch = Chapter(
            story_id=story.story_id,
            chapter_number=ch_def["number"],
            title=ch_def["title"],
            content=ch_def["content"],
        )
        db.add(ch)
        db.flush()
        chapter_ids[ch_def["number"]] = ch.chapter_id

    db.commit()

    for ch_def in CHAPTERS:
        plain = _html_to_plain(ch_def["content"])
        await embed_and_store_chunks(
            chapter_ids[ch_def["number"]], story.story_id, ch_def["number"], plain, db,
        )

    return {"user_id": user.user_id, "story_id": story.story_id, "chapter_ids": chapter_ids}


def cleanup_fixture(db, story_id: str, user_id: str):
    """Delete the fixture via ORM cascade and assert zero orphan rows remain."""
    from sqlalchemy import text as sqltext
    from models import Story, User

    s = db.query(Story).filter(Story.story_id == story_id).first()
    if s:
        db.delete(s)
    u = db.query(User).filter(User.user_id == user_id).first()
    if u:
        db.delete(u)
    db.commit()

    rows = db.execute(sqltext("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema='public' AND column_name IN ('story_id','user_id')
    """)).fetchall()
    orphans = []
    for table_name, column_name in rows:
        val = story_id if column_name == "story_id" else user_id
        cnt = db.execute(
            sqltext(f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" = :v'),
            {"v": val},
        ).scalar()
        if cnt:
            orphans.append((table_name, column_name, cnt))
    if orphans:
        raise AssertionError(f"orphan rows left behind by retrieval fixture cleanup: {orphans}")
