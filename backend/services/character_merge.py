"""
Character deduplication / consolidation — task 4.8.

Merges a `duplicate` Character into a `survivor` Character, moving every
piece of data 4.8's enumeration found referencing `characters.character_id`
(direct FKs and denormalized JSON arrays alike) so nothing is silently
orphaned or lost, then deletes the duplicate row.

Survivor/merge rules (deterministic, in order):
  1. Character itself      — survivor's name/role/status win, UNLESS the
                              duplicate's role/status ranks strictly higher
                              on the existing _ROLE_PRIORITY/_STATUS_PRIORITY
                              scale (reused from ai_service.py's cast-merge,
                              for consistency with how cast generation
                              already resolves the same kind of conflict).
                              Aliases are unioned (survivor ∪ duplicate ∪
                              duplicate's old name), deduplicated case-
                              insensitively, preserving order.
  2. CharacterProfile (1:1) — field-by-field, richer (non-empty) value wins;
                              survivor's non-empty value is never overwritten
                              by a merely-present duplicate value. traits
                              lists are unioned. If survivor has no profile
                              row, the duplicate's profile is adopted (its
                              character_id is repointed) rather than merged
                              field-by-field, since there's nothing to merge
                              against.
  3. CharacterIntelligence (1:1) — NOT field-merged: this is Qwen-derived
                              analysis of a single character's arc, not
                              author-editable facts, so splicing two
                              characters' scores/arcs together would
                              fabricate an analysis nobody generated. The
                              survivor's row (if present, else the
                              duplicate's, adopted) is kept and marked
                              is_stale=True so it regenerates against the
                              merged character on next analysis.
  4. CharacterArcSnapshot   — one row per (character, chapter). For a
     (per chapter, FK,       chapter where only the duplicate has a
      UNIQUE(char,chapter))  snapshot, it's reassigned to the survivor. For a
                              chapter where BOTH have one, the duplicate's is
                              left in place and cascade-deleted with the
                              duplicate character (its own row, not
                              reassignable without violating the unique
                              constraint) — the survivor's is kept as-is.
  5. CharacterMention       — always reassigned (this is appearance
     (per mention, FK)       evidence, not curated 1:1 data — merging two
                              characters means their combined mention
                              history belongs to the survivor).
  6. CharacterRelationship  — for each edge touching the duplicate, the
     (FK, UNIQUE(story,      endpoint is rewritten to the survivor. If that
      from,to,type))         would create a self-relationship (survivor↔
                              survivor) or collide with an edge the survivor
                              already has (same rewritten from/to/type), the
                              duplicate's edge is dropped instead (kept
                              instead of reassigned would violate the unique
                              constraint or be nonsensical).
  7. RelationshipIntelligence — kept in lockstep with whatever happened to
     (FK to character +       its parent CharacterRelationship row in step 6:
      denormalized FK to      reassigned alongside a reassigned edge, deleted
      character_relationships alongside a dropped edge.
      via relationship_id)
  8. chapter_chunks.character_ids,
     chapter_summaries.character_ids,
     character_mentions.co_character_ids
                              — denormalized JSON arrays of character_id,
                              NOT FK-enforced (so a stale reference here would
                              not error, it would just silently be wrong).
                              Every occurrence of duplicate_id across the
                              whole story is replaced with survivor_id and
                              deduplicated.

Transactional: every write here uses the SAME `db` session and is not
committed until the very end (one `db.commit()`), and the caller is expected
to run this inside a try/except that rolls back on any exception — so a
failure partway through leaves the database exactly as it was, never a
partial merge. See tests/test_character_merge.py for the rollback proof.

Never touches which chunks/summaries text says — only which character_id
values point at which row. Never called on real author data in this
project's own test suite — every test uses disposable, self-labelled
fixtures (see tests/test_character_merge.py).
"""
from __future__ import annotations

from typing import Optional

_ROLE_PRIORITY   = {"protagonist": 3, "antagonist": 2, "supporting": 1, "minor": 0}
_STATUS_PRIORITY = {"deceased": 2, "active": 1, "unknown": 0}

# CharacterProfile fields eligible for "richer (non-empty) value wins".
_PROFILE_TEXT_FIELDS = (
    "age", "appearance", "personality", "motivations", "goals",
    "backstory", "arc_notes", "raw_notes",
)


class MergeError(ValueError):
    """Raised for a merge request that cannot be satisfied — never a partial
    write; the caller's transaction is rolled back on this exception."""


def merge_characters(db, story_id: str, survivor_id: str, duplicate_id: str) -> dict:
    """
    Merge `duplicate_id` into `survivor_id` within `story_id`. Returns a
    summary dict describing what moved, for the API response and for tests.

    Does NOT commit. Caller commits (or rolls back) the session.
    """
    from models import (
        Character, CharacterProfile, CharacterIntelligence, CharacterArcSnapshot,
        CharacterMention, CharacterRelationship, RelationshipIntelligence,
        ChapterChunk, ChapterSummary,
    )

    if survivor_id == duplicate_id:
        raise MergeError("Cannot merge a character with itself.")

    survivor = db.query(Character).filter(
        Character.character_id == survivor_id, Character.story_id == story_id,
    ).first()
    duplicate = db.query(Character).filter(
        Character.character_id == duplicate_id, Character.story_id == story_id,
    ).first()
    if not survivor:
        raise MergeError(f"Survivor character {survivor_id} not found in this story.")
    if not duplicate:
        raise MergeError(f"Duplicate character {duplicate_id} not found in this story.")

    summary: dict = {
        "survivor_id": survivor_id, "duplicate_id": duplicate_id,
        "duplicate_name": duplicate.name,
    }

    # ── 1. Character record ────────────────────────────────────────────────
    if _ROLE_PRIORITY.get(duplicate.role, -1) > _ROLE_PRIORITY.get(survivor.role, -1):
        survivor.role = duplicate.role
    if _STATUS_PRIORITY.get(duplicate.status, -1) > _STATUS_PRIORITY.get(survivor.status, -1):
        survivor.status = duplicate.status

    existing_aliases_lower = {a.strip().lower() for a in (survivor.aliases or [])}
    existing_aliases_lower.add(survivor.name.strip().lower())
    merged_aliases = list(survivor.aliases or [])
    for candidate in [duplicate.name, *(duplicate.aliases or [])]:
        c = (candidate or "").strip()
        if c and c.lower() not in existing_aliases_lower:
            merged_aliases.append(c)
            existing_aliases_lower.add(c.lower())
    survivor.aliases = merged_aliases
    summary["merged_aliases"] = merged_aliases

    # ── 2. CharacterProfile (1:1) ──────────────────────────────────────────
    survivor_profile = db.query(CharacterProfile).filter(
        CharacterProfile.character_id == survivor_id
    ).first()
    duplicate_profile = db.query(CharacterProfile).filter(
        CharacterProfile.character_id == duplicate_id
    ).first()
    if duplicate_profile and not survivor_profile:
        duplicate_profile.character_id = survivor_id
        summary["profile"] = "adopted duplicate's profile (survivor had none)"
    elif duplicate_profile and survivor_profile:
        for field in _PROFILE_TEXT_FIELDS:
            if not (getattr(survivor_profile, field) or "").strip():
                dup_val = (getattr(duplicate_profile, field) or "").strip()
                if dup_val:
                    setattr(survivor_profile, field, dup_val)
        survivor_traits = list(survivor_profile.traits or [])
        seen = {t.strip().lower() for t in survivor_traits}
        for t in (duplicate_profile.traits or []):
            if t and t.strip().lower() not in seen:
                survivor_traits.append(t)
                seen.add(t.strip().lower())
        survivor_profile.traits = survivor_traits
        # duplicate_profile row is left as-is — cascade-deleted with `duplicate`
        # (Character.profile has cascade="all, delete-orphan").
        summary["profile"] = "merged fields into survivor's profile (richer wins)"
    else:
        summary["profile"] = "nothing to merge"
    db.flush()  # same cascade-collection reason as the arc-snapshot flush below

    # ── 3. CharacterIntelligence (1:1) — not field-merged, see module docstring ─
    survivor_intel = db.query(CharacterIntelligence).filter(
        CharacterIntelligence.character_id == survivor_id
    ).first()
    duplicate_intel = db.query(CharacterIntelligence).filter(
        CharacterIntelligence.character_id == duplicate_id
    ).first()
    if survivor_intel:
        survivor_intel.is_stale = True
        summary["intelligence"] = "kept survivor's, marked stale for regeneration"
    elif duplicate_intel:
        duplicate_intel.character_id = survivor_id
        duplicate_intel.is_stale = True
        summary["intelligence"] = "adopted duplicate's, marked stale for regeneration"
    else:
        summary["intelligence"] = "neither had one"
    db.flush()  # same cascade-collection reason

    # ── 4. CharacterArcSnapshot — per (character, chapter) ─────────────────
    survivor_chapters = {
        row.chapter_id for row in
        db.query(CharacterArcSnapshot.chapter_id)
        .filter(CharacterArcSnapshot.character_id == survivor_id).all()
    }
    dup_snapshots = db.query(CharacterArcSnapshot).filter(
        CharacterArcSnapshot.character_id == duplicate_id
    ).all()
    reassigned_snapshots = 0
    for snap in dup_snapshots:
        if snap.chapter_id in survivor_chapters:
            continue  # survivor already has one for this chapter — leave duplicate's
                      # row to be cascade-deleted with the duplicate character.
        snap.character_id = survivor_id
        reassigned_snapshots += 1
    summary["arc_snapshots_reassigned"] = reassigned_snapshots
    summary["arc_snapshots_dropped"] = len(dup_snapshots) - reassigned_snapshots
    # Flush now: Character.arc_snapshots has cascade="all, delete-orphan", which
    # cascades based on the relationship's collection state. Without this flush,
    # `db.delete(duplicate)` below can still see a reassigned snapshot as part of
    # duplicate's collection (the raw FK write above hasn't been reconciled with
    # the ORM's relationship bookkeeping yet) and delete it anyway — silently
    # discarding a row this function just decided to keep.
    db.flush()

    # ── 5. CharacterMention — always reassigned (appearance evidence) ──────
    n_mentions = (
        db.query(CharacterMention)
        .filter(CharacterMention.character_id == duplicate_id)
        .update({CharacterMention.character_id: survivor_id}, synchronize_session=False)
    )
    summary["mentions_reassigned"] = n_mentions

    # ── 6 + 7. CharacterRelationship + RelationshipIntelligence ────────────
    existing_edges = {
        (r.from_character_id, r.to_character_id, r.relationship_type)
        for r in db.query(CharacterRelationship).filter(
            CharacterRelationship.story_id == story_id,
        ).all()
    }
    touched = db.query(CharacterRelationship).filter(
        CharacterRelationship.story_id == story_id,
        (CharacterRelationship.from_character_id == duplicate_id) |
        (CharacterRelationship.to_character_id == duplicate_id),
    ).all()

    relationships_reassigned = 0
    relationships_dropped = 0
    for rel in touched:
        new_from = survivor_id if rel.from_character_id == duplicate_id else rel.from_character_id
        new_to   = survivor_id if rel.to_character_id   == duplicate_id else rel.to_character_id

        related_intel = db.query(RelationshipIntelligence).filter(
            RelationshipIntelligence.relationship_id == rel.relationship_id
        ).all()

        if new_from == new_to or (new_from, new_to, rel.relationship_type) in existing_edges:
            # Self-relationship after substitution, or a duplicate of an edge
            # the survivor already has — drop this edge and its intel rows.
            for ri in related_intel:
                db.delete(ri)
            db.delete(rel)
            relationships_dropped += 1
        else:
            rel.from_character_id = new_from
            rel.to_character_id   = new_to
            for ri in related_intel:
                ri.from_character_id = new_from
                ri.to_character_id   = new_to
            existing_edges.add((new_from, new_to, rel.relationship_type))
            relationships_reassigned += 1
    summary["relationships_reassigned"] = relationships_reassigned
    summary["relationships_dropped"] = relationships_dropped

    # ── 8. Denormalized character_id JSON arrays across the story ──────────
    def _swap_ids(id_list: Optional[list]) -> tuple[list, bool]:
        if not id_list:
            return (id_list or [], False)
        if duplicate_id not in id_list:
            return (id_list, False)
        out, seen = [], set()
        for cid in id_list:
            new_cid = survivor_id if cid == duplicate_id else cid
            if new_cid not in seen:
                out.append(new_cid)
                seen.add(new_cid)
        return (out, True)

    chunks_updated = 0
    for chunk in db.query(ChapterChunk).filter(
        ChapterChunk.story_id == story_id,
        ChapterChunk.character_ids.isnot(None),
    ).all():
        new_ids, changed = _swap_ids(chunk.character_ids)
        if changed:
            chunk.character_ids = new_ids
            chunks_updated += 1

    summaries_updated = 0
    for cs in db.query(ChapterSummary).filter(
        ChapterSummary.story_id == story_id,
        ChapterSummary.character_ids.isnot(None),
    ).all():
        new_ids, changed = _swap_ids(cs.character_ids)
        if changed:
            cs.character_ids = new_ids
            summaries_updated += 1

    co_mentions_updated = 0
    for m in db.query(CharacterMention).filter(
        CharacterMention.story_id == story_id,
        CharacterMention.co_character_ids.isnot(None),
    ).all():
        new_ids, changed = _swap_ids(m.co_character_ids)
        if changed:
            m.co_character_ids = new_ids
            co_mentions_updated += 1

    summary["chunks_updated"] = chunks_updated
    summary["summaries_updated"] = summaries_updated
    summary["co_mentions_updated"] = co_mentions_updated

    # ── Delete the duplicate ────────────────────────────────────────────────
    # By this point: relationships have been reassigned/dropped explicitly
    # (not covered by ORM cascade); profile/intelligence/arc_snapshots/
    # mentions still attached to `duplicate` are exactly the ones this
    # function decided NOT to move, and Character's own cascade
    # ("all, delete-orphan" on profile/mentions/arc_snapshots/intelligence)
    # removes them together with the row.
    db.delete(duplicate)
    db.flush()

    return summary
