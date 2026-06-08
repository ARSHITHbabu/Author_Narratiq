"""Story Intelligence System V1+V2 — 23 new tables

Revision ID: 0007
Revises: 0002
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TEXT, JSON

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── story_intel_jobs ──────────────────────────────────────────────────────
    op.create_table(
        "story_intel_jobs",
        sa.Column("job_id",           sa.String(), primary_key=True),
        sa.Column("story_id",         sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id",          sa.String(), sa.ForeignKey("users.user_id",   ondelete="CASCADE"), nullable=False),
        sa.Column("status",           sa.String(), nullable=False, server_default="pending"),
        sa.Column("triggered_by",     sa.String(), nullable=False, server_default="manual"),
        sa.Column("passes_requested", sa.JSON(),   nullable=True),
        sa.Column("passes_completed", sa.JSON(),   nullable=True),
        sa.Column("passes_failed",    sa.JSON(),   nullable=True),
        sa.Column("current_pass",     sa.String(), nullable=True, server_default=""),
        sa.Column("percent",          sa.Integer(),nullable=True, server_default="0"),
        sa.Column("error_message",    sa.Text(),   nullable=True, server_default=""),
        sa.Column("created_at",       sa.DateTime(),nullable=True),
        sa.Column("updated_at",       sa.DateTime(),nullable=True),
    )
    op.create_index("ix_story_intel_jobs_story_id", "story_intel_jobs", ["story_id"])

    # ── story_genre_hierarchy ─────────────────────────────────────────────────
    op.create_table(
        "story_genre_hierarchy",
        sa.Column("genre_id",                 sa.String(), primary_key=True),
        sa.Column("story_id",                 sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("primary_genre",            sa.String(), nullable=True, server_default=""),
        sa.Column("primary_genre_confidence", sa.Float(),  nullable=True, server_default="0"),
        sa.Column("secondary_genres",         sa.JSON(),   nullable=True),
        sa.Column("genre_blend_rationale",    sa.Text(),   nullable=True, server_default=""),
        sa.Column("marketing_category",       sa.String(), nullable=True, server_default=""),
        sa.Column("comparable_titles",        sa.JSON(),   nullable=True),
        sa.Column("tone_markers",             sa.JSON(),   nullable=True),
        sa.Column("author_overrides",         sa.JSON(),   nullable=True),
        sa.Column("is_stale",                 sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",               sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",             sa.DateTime(),nullable=True),
    )

    # ── story_dna ─────────────────────────────────────────────────────────────
    op.create_table(
        "story_dna",
        sa.Column("dna_id",                sa.String(), primary_key=True),
        sa.Column("story_id",              sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("premise",               sa.Text(),   nullable=True, server_default=""),
        sa.Column("central_question",      sa.Text(),   nullable=True, server_default=""),
        sa.Column("thematic_core",         sa.Text(),   nullable=True, server_default=""),
        sa.Column("narrative_engine",      sa.Text(),   nullable=True, server_default=""),
        sa.Column("story_promise",         sa.Text(),   nullable=True, server_default=""),
        sa.Column("resolution_type",       sa.Text(),   nullable=True, server_default=""),
        sa.Column("pov_style",             sa.String(), nullable=True, server_default=""),
        sa.Column("tense",                 sa.String(), nullable=True, server_default=""),
        sa.Column("sentence_rhythm",       sa.String(), nullable=True, server_default=""),
        sa.Column("vocabulary_tier",       sa.String(), nullable=True, server_default=""),
        sa.Column("prose_style",           sa.Text(),   nullable=True, server_default=""),
        sa.Column("structural_complexity", sa.String(), nullable=True, server_default=""),
        sa.Column("chapter_dna",           sa.JSON(),   nullable=True),
        sa.Column("confidence",            sa.Float(),  nullable=True, server_default="0"),
        sa.Column("author_overrides",      sa.JSON(),   nullable=True),
        sa.Column("is_stale",              sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",            sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",          sa.DateTime(),nullable=True),
    )

    # ── story_audience_profile ────────────────────────────────────────────────
    op.create_table(
        "story_audience_profile",
        sa.Column("audience_id",           sa.String(), primary_key=True),
        sa.Column("story_id",              sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("primary_audience",      sa.String(), nullable=True, server_default=""),
        sa.Column("age_range",             sa.String(), nullable=True, server_default=""),
        sa.Column("reading_level",         sa.String(), nullable=True, server_default=""),
        sa.Column("content_warnings",      sa.JSON(),   nullable=True),
        sa.Column("appeal_factors",        sa.JSON(),   nullable=True),
        sa.Column("comparable_readership", sa.JSON(),   nullable=True),
        sa.Column("marketing_hooks",       sa.JSON(),   nullable=True),
        sa.Column("author_overrides",      sa.JSON(),   nullable=True),
        sa.Column("is_stale",              sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",            sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",          sa.DateTime(),nullable=True),
    )

    # ── story_themes ──────────────────────────────────────────────────────────
    op.create_table(
        "story_themes",
        sa.Column("theme_id",          sa.String(), primary_key=True),
        sa.Column("story_id",          sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("primary_theme",     sa.Text(),   nullable=True, server_default=""),
        sa.Column("theme_statement",   sa.Text(),   nullable=True, server_default=""),
        sa.Column("secondary_themes",  sa.JSON(),   nullable=True),
        sa.Column("motifs",            sa.JSON(),   nullable=True),
        sa.Column("symbols",           sa.JSON(),   nullable=True),
        sa.Column("thematic_arc",      sa.Text(),   nullable=True, server_default=""),
        sa.Column("chapter_theme_map", sa.JSON(),   nullable=True),
        sa.Column("author_overrides",  sa.JSON(),   nullable=True),
        sa.Column("is_stale",          sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",        sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",      sa.DateTime(),nullable=True),
    )

    # ── story_conflicts ───────────────────────────────────────────────────────
    op.create_table(
        "story_conflicts",
        sa.Column("conflict_id",              sa.String(), primary_key=True),
        sa.Column("story_id",                 sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("primary_conflict",         sa.Text(),   nullable=True, server_default=""),
        sa.Column("conflict_type",            sa.String(), nullable=True, server_default=""),
        sa.Column("secondary_conflicts",      sa.JSON(),   nullable=True),
        sa.Column("conflict_evolution",       sa.JSON(),   nullable=True),
        sa.Column("unresolved_conflicts",     sa.JSON(),   nullable=True),
        sa.Column("conflict_resolution_path", sa.Text(),   nullable=True, server_default=""),
        sa.Column("chapter_conflict_map",     sa.JSON(),   nullable=True),
        sa.Column("author_overrides",         sa.JSON(),   nullable=True),
        sa.Column("is_stale",                 sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",               sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",             sa.DateTime(),nullable=True),
    )

    # ── story_world_profile ───────────────────────────────────────────────────
    op.create_table(
        "story_world_profile",
        sa.Column("world_id",           sa.String(), primary_key=True),
        sa.Column("story_id",           sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("setting_type",       sa.String(), nullable=True, server_default=""),
        sa.Column("primary_settings",   sa.JSON(),   nullable=True),
        sa.Column("world_rules",        sa.JSON(),   nullable=True),
        sa.Column("time_period",        sa.String(), nullable=True, server_default=""),
        sa.Column("social_structure",   sa.Text(),   nullable=True, server_default=""),
        sa.Column("technology_level",   sa.String(), nullable=True, server_default=""),
        sa.Column("magic_system",       sa.JSON(),   nullable=True),
        sa.Column("cultural_elements",  sa.JSON(),   nullable=True),
        sa.Column("consistency_issues", sa.JSON(),   nullable=True),
        sa.Column("author_overrides",   sa.JSON(),   nullable=True),
        sa.Column("is_stale",           sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",         sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",       sa.DateTime(),nullable=True),
    )

    # ── story_narrative_structure ─────────────────────────────────────────────
    op.create_table(
        "story_narrative_structure",
        sa.Column("structure_id",              sa.String(),  primary_key=True),
        sa.Column("story_id",                  sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("structure_type",            sa.String(),  nullable=True, server_default=""),
        sa.Column("act_breakdown",             sa.JSON(),    nullable=True),
        sa.Column("inciting_incident_chapter", sa.Integer(), nullable=True),
        sa.Column("midpoint_chapter",          sa.Integer(), nullable=True),
        sa.Column("climax_chapter",            sa.Integer(), nullable=True),
        sa.Column("resolution_chapter",        sa.Integer(), nullable=True),
        sa.Column("narrative_promises",        sa.JSON(),    nullable=True),
        sa.Column("promises_kept",             sa.JSON(),    nullable=True),
        sa.Column("promises_broken",           sa.JSON(),    nullable=True),
        sa.Column("structural_issues",         sa.JSON(),    nullable=True),
        sa.Column("author_overrides",          sa.JSON(),    nullable=True),
        sa.Column("is_stale",                  sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("input_hash",                sa.String(),  nullable=True, server_default=""),
        sa.Column("generated_at",              sa.DateTime(),nullable=True),
    )

    # ── story_emotional_arc ───────────────────────────────────────────────────
    op.create_table(
        "story_emotional_arc",
        sa.Column("arc_id",                    sa.String(), primary_key=True),
        sa.Column("story_id",                  sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_arc_shape",         sa.String(), nullable=True, server_default=""),
        sa.Column("opening_emotion",           sa.String(), nullable=True, server_default=""),
        sa.Column("midpoint_emotion",          sa.String(), nullable=True, server_default=""),
        sa.Column("climax_emotion",            sa.String(), nullable=True, server_default=""),
        sa.Column("resolution_emotion",        sa.String(), nullable=True, server_default=""),
        sa.Column("emotional_contrast_score",  sa.Float(),  nullable=True, server_default="0"),
        sa.Column("chapter_emotions",          sa.JSON(),   nullable=True),
        sa.Column("dominant_emotions",         sa.JSON(),   nullable=True),
        sa.Column("emotional_gaps",            sa.JSON(),   nullable=True),
        sa.Column("author_overrides",          sa.JSON(),   nullable=True),
        sa.Column("is_stale",                  sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",                sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",              sa.DateTime(),nullable=True),
    )

    # ── story_pacing_map ──────────────────────────────────────────────────────
    op.create_table(
        "story_pacing_map",
        sa.Column("pacing_id",       sa.String(), primary_key=True),
        sa.Column("story_id",        sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_pacing",  sa.String(), nullable=True, server_default=""),
        sa.Column("act_structure",   sa.JSON(),   nullable=True),
        sa.Column("chapter_pacing",  sa.JSON(),   nullable=True),
        sa.Column("slow_zones",      sa.JSON(),   nullable=True),
        sa.Column("tension_peaks",   sa.JSON(),   nullable=True),
        sa.Column("pacing_score",    sa.Float(),  nullable=True, server_default="0"),
        sa.Column("pacing_issues",   sa.JSON(),   nullable=True),
        sa.Column("author_overrides",sa.JSON(),   nullable=True),
        sa.Column("is_stale",        sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",      sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",    sa.DateTime(),nullable=True),
    )

    # ── story_strength_indicators ─────────────────────────────────────────────
    op.create_table(
        "story_strength_indicators",
        sa.Column("strength_id",            sa.String(), primary_key=True),
        sa.Column("story_id",               sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_score",          sa.Float(),  nullable=True, server_default="0"),
        sa.Column("voice_score",            sa.Float(),  nullable=True, server_default="0"),
        sa.Column("originality_score",      sa.Float(),  nullable=True, server_default="0"),
        sa.Column("character_depth_score",  sa.Float(),  nullable=True, server_default="0"),
        sa.Column("plot_coherence_score",   sa.Float(),  nullable=True, server_default="0"),
        sa.Column("pacing_score",           sa.Float(),  nullable=True, server_default="0"),
        sa.Column("world_building_score",   sa.Float(),  nullable=True, server_default="0"),
        sa.Column("dialogue_quality_score", sa.Float(),  nullable=True, server_default="0"),
        sa.Column("strengths",              sa.JSON(),   nullable=True),
        sa.Column("score_rationale",        sa.JSON(),   nullable=True),
        sa.Column("author_overrides",       sa.JSON(),   nullable=True),
        sa.Column("is_stale",               sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",             sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",           sa.DateTime(),nullable=True),
    )

    # ── story_risk_register ───────────────────────────────────────────────────
    op.create_table(
        "story_risk_register",
        sa.Column("risk_id",                   sa.String(), primary_key=True),
        sa.Column("story_id",                  sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plot_holes",                sa.JSON(),   nullable=True),
        sa.Column("continuity_risks",          sa.JSON(),   nullable=True),
        sa.Column("character_inconsistencies", sa.JSON(),   nullable=True),
        sa.Column("pacing_risks",              sa.JSON(),   nullable=True),
        sa.Column("tonal_shifts",              sa.JSON(),   nullable=True),
        sa.Column("unresolved_threads",        sa.JSON(),   nullable=True),
        sa.Column("risk_score",                sa.Float(),  nullable=True, server_default="0"),
        sa.Column("critical_issues",           sa.JSON(),   nullable=True),
        sa.Column("author_overrides",          sa.JSON(),   nullable=True),
        sa.Column("is_stale",                  sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",                sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",              sa.DateTime(),nullable=True),
    )

    # ── story_foreshadowing_registry ──────────────────────────────────────────
    op.create_table(
        "story_foreshadowing_registry",
        sa.Column("foreshadow_id",           sa.String(), primary_key=True),
        sa.Column("story_id",                sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("active_foreshadowings",   sa.JSON(),   nullable=True),
        sa.Column("resolved_foreshadowings", sa.JSON(),   nullable=True),
        sa.Column("orphaned_hints",          sa.JSON(),   nullable=True),
        sa.Column("payoffs_without_setup",   sa.JSON(),   nullable=True),
        sa.Column("is_stale",                sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",              sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",            sa.DateTime(),nullable=True),
    )

    # ── story_continuity_risks ────────────────────────────────────────────────
    op.create_table(
        "story_continuity_risks",
        sa.Column("continuity_id",                sa.String(), primary_key=True),
        sa.Column("story_id",                     sa.String(), sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("character_continuity_issues",  sa.JSON(),   nullable=True),
        sa.Column("world_continuity_issues",      sa.JSON(),   nullable=True),
        sa.Column("timeline_continuity_issues",   sa.JSON(),   nullable=True),
        sa.Column("object_continuity_issues",     sa.JSON(),   nullable=True),
        sa.Column("chapter_continuity_map",       sa.JSON(),   nullable=True),
        sa.Column("risk_score",                   sa.Float(),  nullable=True, server_default="0"),
        sa.Column("is_stale",                     sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",                   sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",                 sa.DateTime(),nullable=True),
    )

    # ── story_intel_versions ──────────────────────────────────────────────────
    op.create_table(
        "story_intel_versions",
        sa.Column("version_id",     sa.String(),  primary_key=True),
        sa.Column("story_id",       sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot",       sa.JSON(),    nullable=True),
        sa.Column("trigger",        sa.String(),  nullable=True, server_default="manual"),
        sa.Column("created_at",     sa.DateTime(),nullable=True),
    )
    op.create_index("ix_story_intel_versions_story_id", "story_intel_versions", ["story_id"])

    # ── character_intelligence ────────────────────────────────────────────────
    op.create_table(
        "character_intelligence",
        sa.Column("intel_id",                sa.String(), primary_key=True),
        sa.Column("character_id",            sa.String(), sa.ForeignKey("characters.character_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("story_id",                sa.String(), sa.ForeignKey("stories.story_id",        ondelete="CASCADE"), nullable=False),
        sa.Column("goals",                   sa.JSON(),   nullable=True),
        sa.Column("motivations",             sa.Text(),   nullable=True, server_default=""),
        sa.Column("internal_wounds",         sa.Text(),   nullable=True, server_default=""),
        sa.Column("external_objectives",     sa.JSON(),   nullable=True),
        sa.Column("secrets",                 sa.JSON(),   nullable=True),
        sa.Column("fears",                   sa.JSON(),   nullable=True),
        sa.Column("contradictions",          sa.JSON(),   nullable=True),
        sa.Column("arc_stage",               sa.String(), nullable=True, server_default=""),
        sa.Column("arc_stage_rationale",     sa.Text(),   nullable=True, server_default=""),
        sa.Column("voice_distinction_score", sa.Float(),  nullable=True, server_default="0"),
        sa.Column("voice_markers",           sa.JSON(),   nullable=True),
        sa.Column("plot_influence_score",    sa.Float(),  nullable=True, server_default="0"),
        sa.Column("consistency_score",       sa.Float(),  nullable=True, server_default="0"),
        sa.Column("consistency_issues",      sa.JSON(),   nullable=True),
        sa.Column("memory_timeline",         sa.JSON(),   nullable=True),
        sa.Column("confidence",              sa.Float(),  nullable=True, server_default="0"),
        sa.Column("author_overrides",        sa.JSON(),   nullable=True),
        sa.Column("is_stale",                sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",              sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",            sa.DateTime(),nullable=True),
    )
    op.create_index("ix_char_intel_story_id", "character_intelligence", ["story_id"])

    # ── relationship_intelligence ─────────────────────────────────────────────
    op.create_table(
        "relationship_intelligence",
        sa.Column("intel_id",             sa.String(), primary_key=True),
        sa.Column("relationship_id",      sa.String(), sa.ForeignKey("character_relationships.relationship_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("story_id",             sa.String(), sa.ForeignKey("stories.story_id",        ondelete="CASCADE"), nullable=False),
        sa.Column("from_character_id",    sa.String(), sa.ForeignKey("characters.character_id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_character_id",      sa.String(), sa.ForeignKey("characters.character_id", ondelete="CASCADE"), nullable=False),
        sa.Column("evolution_trajectory", sa.Text(),   nullable=True, server_default=""),
        sa.Column("turning_points",       sa.JSON(),   nullable=True),
        sa.Column("tension_score",        sa.Float(),  nullable=True, server_default="0"),
        sa.Column("trust_score",          sa.Float(),  nullable=True, server_default="0"),
        sa.Column("conflict_score",       sa.Float(),  nullable=True, server_default="0"),
        sa.Column("dependency_score",     sa.Float(),  nullable=True, server_default="0"),
        sa.Column("is_hidden",            sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("hidden_reason",        sa.Text(),   nullable=True, server_default=""),
        sa.Column("impact_on_plot",       sa.Text(),   nullable=True, server_default=""),
        sa.Column("history",              sa.JSON(),   nullable=True),
        sa.Column("confidence",           sa.Float(),  nullable=True, server_default="0"),
        sa.Column("author_overrides",     sa.JSON(),   nullable=True),
        sa.Column("is_stale",             sa.Boolean(),nullable=True, server_default="false"),
        sa.Column("input_hash",           sa.String(), nullable=True, server_default=""),
        sa.Column("generated_at",         sa.DateTime(),nullable=True),
    )
    op.create_index("ix_rel_intel_story_id", "relationship_intelligence", ["story_id"])

    # ── story_memory_entries ──────────────────────────────────────────────────
    try:
        from pgvector.sqlalchemy import Vector as PGVector
        vector_col = sa.Column("embedding", PGVector(1024), nullable=True)
    except Exception:
        vector_col = sa.Column("embedding", sa.Text(), nullable=True)

    op.create_table(
        "story_memory_entries",
        sa.Column("entry_id",                  sa.String(),  primary_key=True),
        sa.Column("story_id",                  sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type",               sa.String(),  nullable=False),
        sa.Column("memory_key",                sa.String(),  nullable=False),
        sa.Column("entity_type",               sa.String(),  nullable=True, server_default=""),
        sa.Column("entity_id",                 sa.String(),  nullable=True, server_default=""),
        sa.Column("content",                   sa.Text(),    nullable=False),
        sa.Column("chapter_first_established", sa.Integer(), nullable=True),
        sa.Column("chapter_last_updated",      sa.Integer(), nullable=True),
        sa.Column("importance",                sa.Float(),   nullable=True, server_default="0.5"),
        sa.Column("is_active",                 sa.Boolean(), nullable=True, server_default="true"),
        vector_col,
        sa.Column("is_ai_generated",           sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("is_author_added",           sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("created_at",                sa.DateTime(),nullable=True),
        sa.Column("updated_at",                sa.DateTime(),nullable=True),
        sa.UniqueConstraint("story_id", "memory_key", name="uq_story_memory_key"),
    )
    op.create_index("ix_memory_story_id",   "story_memory_entries", ["story_id"])
    op.create_index("ix_memory_type",       "story_memory_entries", ["memory_type"])
    op.create_index("ix_memory_entity_id",  "story_memory_entries", ["entity_id"])

    # ── story_timeline ────────────────────────────────────────────────────────
    op.create_table(
        "story_timeline",
        sa.Column("timeline_id",              sa.String(),  primary_key=True),
        sa.Column("story_id",                 sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("timeline_type",            sa.String(),  nullable=True, server_default="linear"),
        sa.Column("estimated_story_duration", sa.String(),  nullable=True, server_default=""),
        sa.Column("start_period",             sa.String(),  nullable=True, server_default=""),
        sa.Column("end_period",               sa.String(),  nullable=True, server_default=""),
        sa.Column("seasons_mentioned",        sa.JSON(),    nullable=True),
        sa.Column("significant_time_gaps",    sa.JSON(),    nullable=True),
        sa.Column("character_age_map",        sa.JSON(),    nullable=True),
        sa.Column("contradictions",           sa.JSON(),    nullable=True),
        sa.Column("contradictions_detected",  sa.Integer(), nullable=True, server_default="0"),
        sa.Column("confidence",               sa.Float(),   nullable=True, server_default="0"),
        sa.Column("is_stale",                 sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("input_hash",               sa.String(),  nullable=True, server_default=""),
        sa.Column("generated_at",             sa.DateTime(),nullable=True),
    )

    # ── story_timeline_events ─────────────────────────────────────────────────
    op.create_table(
        "story_timeline_events",
        sa.Column("event_id",             sa.String(),  primary_key=True),
        sa.Column("story_id",             sa.String(),  sa.ForeignKey("stories.story_id",      ondelete="CASCADE"), nullable=False),
        sa.Column("timeline_id",          sa.String(),  sa.ForeignKey("story_timeline.timeline_id", ondelete="SET NULL"), nullable=True),
        sa.Column("chapter_id",           sa.String(),  sa.ForeignKey("chapters.chapter_id",   ondelete="SET NULL"), nullable=True),
        sa.Column("chapter_number",       sa.Integer(), nullable=False),
        sa.Column("event_type",           sa.String(),  nullable=True, server_default="action"),
        sa.Column("story_date",           sa.String(),  nullable=True, server_default=""),
        sa.Column("temporal_marker",      sa.String(),  nullable=True, server_default=""),
        sa.Column("characters_involved",  sa.JSON(),    nullable=True),
        sa.Column("location",             sa.String(),  nullable=True, server_default=""),
        sa.Column("event_description",    sa.Text(),    nullable=True, server_default=""),
        sa.Column("is_flashback",         sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("is_flashforward",      sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("flash_origin_chapter", sa.Integer(), nullable=True),
        sa.Column("is_stale",             sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("generated_at",         sa.DateTime(),nullable=True),
    )
    op.create_index("ix_timeline_events_story_id",  "story_timeline_events", ["story_id"])
    op.create_index("ix_timeline_events_chapter_no","story_timeline_events", ["chapter_number"])

    # ── story_graph_nodes ─────────────────────────────────────────────────────
    try:
        from pgvector.sqlalchemy import Vector as PGVector2
        node_vec_col = sa.Column("embedding", PGVector2(1024), nullable=True)
    except Exception:
        node_vec_col = sa.Column("embedding", sa.Text(), nullable=True)

    op.create_table(
        "story_graph_nodes",
        sa.Column("node_id",            sa.String(),  primary_key=True),
        sa.Column("story_id",           sa.String(),  sa.ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type",          sa.String(),  nullable=False),
        sa.Column("label",              sa.String(),  nullable=False),
        sa.Column("entity_id",          sa.String(),  nullable=True, server_default=""),
        sa.Column("properties",         sa.JSON(),    nullable=True),
        node_vec_col,
        sa.Column("chapter_introduced", sa.Integer(), nullable=True),
        sa.Column("is_active",          sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("created_at",         sa.DateTime(),nullable=True),
    )
    op.create_index("ix_graph_nodes_story_id",  "story_graph_nodes", ["story_id"])
    op.create_index("ix_graph_nodes_node_type", "story_graph_nodes", ["node_type"])
    op.create_index("ix_graph_nodes_entity_id", "story_graph_nodes", ["entity_id"])

    # ── story_graph_edges ─────────────────────────────────────────────────────
    op.create_table(
        "story_graph_edges",
        sa.Column("edge_id",              sa.String(), primary_key=True),
        sa.Column("story_id",             sa.String(), sa.ForeignKey("stories.story_id",       ondelete="CASCADE"), nullable=False),
        sa.Column("from_node_id",         sa.String(), sa.ForeignKey("story_graph_nodes.node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id",           sa.String(), sa.ForeignKey("story_graph_nodes.node_id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_type",            sa.String(), nullable=False),
        sa.Column("weight",               sa.Float(),  nullable=True, server_default="1.0"),
        sa.Column("label",                sa.String(), nullable=True, server_default=""),
        sa.Column("chapter_established",  sa.Integer(),nullable=True),
        sa.Column("properties",           sa.JSON(),   nullable=True),
        sa.Column("is_active",            sa.Boolean(),nullable=True, server_default="true"),
        sa.Column("created_at",           sa.DateTime(),nullable=True),
    )
    op.create_index("ix_graph_edges_story_id",  "story_graph_edges", ["story_id"])
    op.create_index("ix_graph_edges_from_node", "story_graph_edges", ["from_node_id"])
    op.create_index("ix_graph_edges_to_node",   "story_graph_edges", ["to_node_id"])


def downgrade() -> None:
    op.drop_table("story_graph_edges")
    op.drop_table("story_graph_nodes")
    op.drop_table("story_timeline_events")
    op.drop_table("story_timeline")
    op.drop_table("story_memory_entries")
    op.drop_table("relationship_intelligence")
    op.drop_table("character_intelligence")
    op.drop_table("story_intel_versions")
    op.drop_table("story_continuity_risks")
    op.drop_table("story_foreshadowing_registry")
    op.drop_table("story_risk_register")
    op.drop_table("story_strength_indicators")
    op.drop_table("story_pacing_map")
    op.drop_table("story_emotional_arc")
    op.drop_table("story_narrative_structure")
    op.drop_table("story_world_profile")
    op.drop_table("story_conflicts")
    op.drop_table("story_themes")
    op.drop_table("story_audience_profile")
    op.drop_table("story_dna")
    op.drop_table("story_genre_hierarchy")
    op.drop_table("story_intel_jobs")
