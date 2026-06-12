"""
Capability Registry (C) — the higher-level abstraction the voice agent reasons
over, sitting ABOVE individual endpoints.

The agent thinks in *capabilities* ("character_analysis", "text_transform"),
each exposing one or more *actions*. An action declares:
  - action_type        : read | write | generate | analyze | destructive | export
  - execution_locus    : "server" (agent pre-runs) or "client" (frontend api.ts)
  - requires_confirmation
  - required / optional : parameter names the ContextResolver must fill
  - client_call         : logical key the frontend voiceActions.ts dispatches on
                          (defaults to "<capability>.<action>")

This is the single source of truth. catalog.py derives FEATURE_CATALOG (phrases)
and INTENT_REGISTRY (intent → capability/action) from it. Routing flow:

    Intent → Capability Resolution → Feature (endpoint) Resolution → Planning

Phase 3 / plugins extend the platform by appending capabilities here only.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# action_type taxonomy
READ = "read"
WRITE = "write"
GENERATE = "generate"
ANALYZE = "analyze"
DESTRUCTIVE = "destructive"
EXPORT = "export"

# action_types that mutate stored content / are irreversible-ish → always confirm
_MUTATING = {WRITE, DESTRUCTIVE, EXPORT}


@dataclass
class ActionSpec:
    action: str
    action_type: str
    description: str
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    execution_locus: str = "client"          # server (server_sync adapter) | client
    requires_confirmation: bool | None = None  # None → derive from action_type
    client_call: str | None = None            # default "<capability>.<action>"
    # Feature/model binding (the agent calls the FEATURE; the feature owns the model)
    model_service: str = ""                   # e.g. "Qwen via ai_transform", "BGE-M3+Qwen"
    required_context: list[str] = field(default_factory=list)   # context bundle fields
    optional_context: list[str] = field(default_factory=list)

    def needs_confirmation(self) -> bool:
        if self.requires_confirmation is not None:
            return self.requires_confirmation
        return self.action_type in _MUTATING


@dataclass
class Capability:
    name: str
    router: str
    description: str
    phrases: list[str]
    actions: dict[str, ActionSpec]


def _cap(name, router, description, phrases, actions) -> Capability:
    amap = {a.action: a for a in actions}
    for a in amap.values():
        if a.client_call is None:
            a.client_call = f"{name}.{a.action}"
    return Capability(name=name, router=router, description=description,
                      phrases=phrases, actions=amap)


# ══════════════════════════════════════════════════════════════════════════════
#  CAPABILITY REGISTRY  (full Phase 1 + Phase 2 coverage)
# ══════════════════════════════════════════════════════════════════════════════

CAPABILITY_REGISTRY: dict[str, Capability] = {c.name: c for c in [

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    _cap("project_mgmt", "projects",
         "Create, list, open, rename, or delete stories/projects.",
         ["create a new story", "start a new novel", "make a thriller called",
          "list my stories", "show my projects", "open the story",
          "rename this story", "delete this story", "remove the project"],
         [ActionSpec("create", WRITE, "Create a new story.", required=["title"], optional=["genre", "description"]),
          ActionSpec("list",   READ,  "List the author's stories.", execution_locus="client"),
          ActionSpec("open",   READ,  "Open/navigate to a story.", required=["story_id"]),
          ActionSpec("rename", WRITE, "Rename a story.", required=["story_id", "title"]),
          ActionSpec("delete", DESTRUCTIVE, "Delete a story.", required=["story_id"])]),

    _cap("chapter_mgmt", "chapters",
         "Create, open, edit chapters; manage versions and summaries.",
         ["create a new chapter", "add chapter", "open chapter three",
          "go to chapter", "edit this chapter", "save a version",
          "show version history", "restore the previous version",
          "sync summaries", "reindex chapters"],
         [ActionSpec("create",   WRITE, "Create a chapter.", required=["story_id"], optional=["title", "content"]),
          ActionSpec("open",     READ,  "Open a chapter.", required=["chapter_id"]),
          ActionSpec("edit",     WRITE, "Replace/overwrite chapter content.", required=["chapter_id", "content"]),
          ActionSpec("versions", READ,  "List chapter versions.", required=["chapter_id"]),
          ActionSpec("restore",  WRITE, "Restore a chapter version.", required=["chapter_id", "version_id"]),
          ActionSpec("delete",   DESTRUCTIVE, "Delete a chapter.", required=["chapter_id"]),
          ActionSpec("sync",     GENERATE, "Sync chapter summaries/embeddings.", required=["story_id"])]),

    _cap("character_mgmt", "characters",
         "Create/update characters, generate cast, search mentions, graph, relationships.",
         ["create a character", "add a new character named", "update character",
          "generate the cast", "auto detect characters", "find where appears",
          "search for character", "show the character graph",
          "explain the relationship between", "character hints"],
         [ActionSpec("create",        WRITE, "Create a character.", required=["story_id", "name"], optional=["role", "status"]),
          ActionSpec("update",        WRITE, "Update a character.", required=["character_id"], optional=["name", "role", "status"]),
          ActionSpec("generate_cast", GENERATE, "Extract a cast from the manuscript.", required=["story_id"]),
          ActionSpec("search",        READ,  "Find a character / its mentions.", required=["story_id"], optional=["query", "character_id"]),
          ActionSpec("graph",         READ,  "Character relationship graph.", required=["story_id"]),
          ActionSpec("relationships", READ,  "List a character's relationships.", required=["story_id", "character_id"])]),

    _cap("character_voice_check", "characters",
         "P2-05 — check a character's dialogue voice consistency.",
         ["check character voice consistency", "is the dialogue consistent",
          "voice check for", "does this character sound consistent"],
         [ActionSpec("analyze", ANALYZE, "Run voice consistency check.", required=["story_id", "character_id"])]),

    _cap("intake_genre", "intake",
         "Story intake: analyze a description, confirm intake, get genre profile.",
         ["set up the story", "analyze my story description", "detect the genre",
          "confirm the intake", "what genre is this", "genre profile"],
         [ActionSpec("analyze",  GENERATE, "Analyze story description → genre.", required=["story_id", "description"]),
          ActionSpec("confirm",  WRITE, "Confirm intake / genre profile.", required=["story_id", "intake_id"]),
          ActionSpec("get",      READ,  "Get the genre profile.", required=["story_id"])]),

    # plot_assistant is now BRAINSTORMING ONLY — factual questions go to story_qa,
    # character questions to character_qa/character_relationship.
    _cap("plot_assistant", "plot_assistant",
         "Brainstorm plot ideas and directions — what could happen next (NOT factual Q&A).",
         ["help me brainstorm", "what should happen next", "give me plot ideas",
          "suggest some plot directions", "where could the story go from here",
          "brainstorm ideas for the next chapter"],
         [ActionSpec("brainstorm", GENERATE, "Generate plot ideas/suggestions.",
                     required=["story_id", "question"], optional=["chapter_id"],
                     model_service="Qwen via plot_assistant (creative mode)",
                     required_context=["story_id"], optional_context=["current_chapter_text"])]),

    # ── Story / character question-answering (the RAG features) ───────────────
    _cap("story_qa", "plot_assistant",
         "Answer factual questions about the story, plot, chapters, or events using RAG.",
         ["what happens in this chapter", "summarize the ending", "what is the story about",
          "explain what happened", "who killed", "what is the main conflict",
          "tell me what happens", "recap the plot so far", "what did they decide"],
         [ActionSpec("ask", ANALYZE, "Answer a story/chapter factual question (RAG).",
                     required=["story_id", "question"], execution_locus="server",
                     requires_confirmation=False,
                     model_service="BGE-M3 retrieval + Qwen via answer_story_question",
                     required_context=["story_id"],
                     optional_context=["current_chapter_text", "chapter_id", "rag_chunks", "note_context"])]),

    _cap("character_qa", "characters",
         "Answer questions about a character — who they are, traits, goals, where they appear.",
         ["who is", "tell me about the character", "what does this character want",
          "what is this character like", "where does the character appear",
          "what are the character's goals", "describe the character"],
         [ActionSpec("ask", ANALYZE, "Answer a character question (character RAG).",
                     required=["story_id", "question"], optional=["character_id"],
                     execution_locus="server", requires_confirmation=False,
                     model_service="BGE-M3 character RAG + Qwen via answer_story_question",
                     required_context=["story_id"], optional_context=["character_context"])]),

    _cap("character_relationship", "characters",
         "Explain how two characters are related using the relationship graph + character RAG.",
         ["what is the relationship between", "how are they related",
          "how do they know each other", "what is the connection between the characters",
          "are they allies or enemies", "describe the relationship between"],
         [ActionSpec("ask", ANALYZE, "Explain a character relationship.",
                     required=["story_id", "question"], execution_locus="server",
                     requires_confirmation=False,
                     model_service="relationship graph (DB) + BGE-M3 RAG + Qwen",
                     required_context=["story_id"], optional_context=["character_context", "relationships"])]),

    _cap("text_transform", "ai_transform",
         "Rewrite selected text: refine, tone shift, emotion, age-adapt, style, translate.",
         ["refine this", "polish this paragraph", "make this darker",
          "make it more suspenseful", "more emotional", "add more emotion",
          "rewrite for young adults", "make it gothic", "translate this to",
          "improve the writing", "rewrite the slow sections"],
         # All transforms run through the ai_transform FEATURE (Qwen). The agent
         # never rewrites prose itself. required_context=selected_text (priority 1).
         [ActionSpec("refine",     GENERATE, "Refine/polish prose.", required=["text"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          # Descriptors are optional: the model usually states them, but "make this
          # darker" should route + run rather than demand a clarification.
          ActionSpec("tone",       GENERATE, "Shift tone.", required=["text"], optional=["tone"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          ActionSpec("emotion",    GENERATE, "Enhance emotion.", required=["text"], optional=["emotion", "intensity"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          ActionSpec("age_adapt",  GENERATE, "Adapt for an age group.", required=["text"], optional=["target_age"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          ActionSpec("style",      GENERATE, "Apply a narrative style.", required=["text"], optional=["style"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          ActionSpec("translate",  GENERATE, "Translate text.", required=["text", "target_language"],
                     model_service="Qwen via ai_transform", required_context=["selected_text"]),
          # Generative sub-step for multi-step plans — also via the ai_transform feature.
          ActionSpec("rewrite_section", GENERATE, "Rewrite a passage to a goal.",
                     required=["text"], optional=["goal", "tone", "emotion"],
                     model_service="Qwen via ai_transform"),
          # Terminal apply step (client writes the rewrite into the chapter):
          ActionSpec("apply_rewrite", WRITE, "Apply a rewrite to the chapter.",
                     required=["chapter_id", "content"], execution_locus="client", requires_confirmation=True)]),

    _cap("manuscript_import", "manuscript",
         "Import a full manuscript file and split it into chapters.",
         ["import a manuscript", "upload my manuscript", "import my book file",
          "load a document into the story"],
         [ActionSpec("guide", READ, "Guide the manuscript upload (opens file picker).", required=["story_id"])]),

    _cap("export", "export",
         "Export the story to DOCX or PDF.",
         ["export this story", "export to pdf", "download my manuscript",
          "export the final manuscript", "save as docx"],
         [ActionSpec("export", EXPORT, "Export the manuscript.", required=["story_id"], optional=["format"])]),

    _cap("search_replace", "search",
         "Exact search, semantic search, and find & replace across the story.",
         ["find all scenes where a character appears", "where does a character appear",
          "find all places a name is mentioned", "search for the phrase",
          "where is the word mentioned", "semantic search for similar passages",
          "replace the name with another", "find and replace text",
          "swap one word for another throughout the story"],
         [ActionSpec("exact",    READ, "Exact text search.", required=["story_id", "query"]),
          ActionSpec("semantic", READ, "Semantic (meaning) search.", required=["story_id", "query"]),
          ActionSpec("replace",  DESTRUCTIVE, "Find & replace text.",
                     required=["story_id", "query", "replacement"], optional=["chapter_id"])]),

    _cap("plot_holes", "plot_holes",
         "Detect plot holes / inconsistencies in the story.",
         ["find plot holes", "what are the plot holes", "any inconsistencies",
          "check for logic problems"],
         [ActionSpec("analyze", ANALYZE, "Detect plot holes.", required=["story_id"])]),

    _cap("manuscript_report", "manuscript_report",
         "Generate a full editorial manuscript report.",
         ["generate a manuscript report", "full editorial report",
          "give me an overall report of the book"],
         [ActionSpec("analyze", ANALYZE, "Generate manuscript report.", required=["story_id"])]),

    _cap("story_intel", "story_intel",
         "Story intelligence: genre, story DNA, audience, themes, etc.",
         ["analyze the story intelligence", "what is the story dna",
          "who is the target audience", "audience analysis",
          "show story themes", "story intelligence dashboard"],
         [ActionSpec("analyze",  GENERATE, "Run intelligence analysis.", required=["story_id"]),
          ActionSpec("dna",      READ, "Get story DNA.", required=["story_id"]),
          ActionSpec("audience", READ, "Get target audience.", required=["story_id"]),
          ActionSpec("genre",    READ, "Get genre hierarchy.", required=["story_id"]),
          ActionSpec("themes",   READ, "Get themes.", required=["story_id"])]),

    _cap("narrative_threads", "narrative_threads",
         "Scan and track plot/subplot threads.",
         ["scan narrative threads", "track the subplots", "list plot threads",
          "what threads are unresolved"],
         [ActionSpec("scan", GENERATE, "Scan narrative threads.", required=["story_id"]),
          ActionSpec("list", READ, "List narrative threads.", required=["story_id"])]),

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    _cap("emotional_arc", "analysis",
         "P2-01 — analyze the story's emotional arc.",
         ["summarize the emotional arc", "show the emotional arc",
          "how does the emotion change", "emotional curve of the story"],
         [ActionSpec("analyze", ANALYZE, "Emotional arc analysis.", required=["story_id"])]),

    _cap("continuation", "writing_tools",
         "P2-02 — generate continuation options for a chapter.",
         ["generate continuation options", "continue this scene",
          "give me three ways to continue", "what comes next in this chapter",
          "continue the chapter"],
         [ActionSpec("generate", GENERATE, "Generate continuation options.",
                     required=["story_id", "chapter_id"], optional=["tail_text"])]),

    _cap("duplicate_scenes", "analysis",
         "P2-03 — detect repeated or near-duplicate scenes that say the same thing twice.",
         ["find duplicate or repeated scenes", "are any scenes too similar to each other",
          "detect redundant scenes", "scenes that repeat the same beat"],
         [ActionSpec("analyze", ANALYZE, "Detect duplicate scenes.", required=["story_id"])]),

    _cap("style_drift", "analysis",
         "P2-04 — detect writing-style drift across chapters.",
         ["check for style drift", "has my style changed", "style consistency",
          "does this chapter have style drift"],
         [ActionSpec("analyze", ANALYZE, "Style drift analysis.", required=["story_id"])]),

    _cap("story_bible", "story_bible",
         "P2-06 — generate a 5-section story bible.",
         ["generate a story bible", "create the story bible", "build a story bible",
          "make a world bible"],
         [ActionSpec("generate", GENERATE, "Generate story bible.", required=["story_id"]),
          ActionSpec("get",      READ, "Get the latest story bible.", required=["story_id"])]),

    _cap("outline", "writing_tools",
         "P2-07 — generate a chapter outline / beat sheet.",
         ["create a beat sheet", "outline this chapter", "generate an outline",
          "scene by scene breakdown", "beat sheet for the chapter"],
         [ActionSpec("generate", GENERATE, "Generate outline / beat sheet.",
                     required=["story_id", "chapter_id", "chapter_goal"], optional=["scene_count"])]),

    _cap("continuity_check", "analysis",
         "P2-08 — cross-chapter continuity check.",
         ["check continuity", "any continuity issues", "continuity problems between",
          "find continuity errors"],
         [ActionSpec("analyze", ANALYZE, "Continuity check.", required=["story_id"])]),

    _cap("pacing_goals", "pacing",
         "P2-09 — set or read pacing goals.",
         ["set a pacing goal", "target words per chapter", "set my word goal",
          "what's my pacing", "how am i pacing"],
         [ActionSpec("set", WRITE, "Set a pacing goal.", required=["story_id"],
                     optional=["target_words_per_chapter", "target_chapter_count", "target_word_count"]),
          ActionSpec("get", READ, "Get pacing goal + progress.", required=["story_id"])]),

    _cap("ocr_inject", "ocr",
         "P2-10 — extract text from an image into the story.",
         ["scan an image", "ocr this photo", "extract text from a picture",
          "import handwritten notes"],
         [ActionSpec("guide", READ, "Guide the OCR image upload (opens file picker).", required=["story_id"])]),

    _cap("voice_note", "audio",
         "P2-11 — save this dictation as a story note (secondary upload→note path retained).",
         ["turn this into a story note", "save this as a note", "make a voice note",
          "add this to my notes", "save my dictation"],
         [ActionSpec("save", WRITE, "Append dictation to a story note.",
                     required=["story_id", "content"], optional=["note_id"])]),

    # ── Account ───────────────────────────────────────────────────────────────
    _cap("account", "auth",
         "Account actions reachable by voice (logout only).",
         ["log me out", "sign out", "log out"],
         [ActionSpec("logout", DESTRUCTIVE, "Log out (clears local session).",
                     execution_locus="client", requires_confirmation=True)]),
]}


def get_capability(name: str) -> Capability | None:
    return CAPABILITY_REGISTRY.get(name)


def get_action(capability: str, action: str) -> ActionSpec | None:
    cap = CAPABILITY_REGISTRY.get(capability)
    if not cap:
        return None
    return cap.actions.get(action)


# ── Deterministic action disambiguation ──────────────────────────────────────
# Once the capability is chosen, strong verb cues in the command pick the action
# reliably — this guards against an LLM (or the shortlist-repair path) turning
# "delete this story" into project_mgmt.create. Cues are ordered: first match
# wins. Listed most-specific first.
import re as _re

ACTION_CUES: dict[str, list[tuple[str, list[str]]]] = {
    "project_mgmt": [
        ("delete", ["delete", "remove", "trash", "get rid of"]),
        ("rename", ["rename", "change the name", "change the title", "retitle"]),
        ("open",   ["open", "go to", "switch to", "load the story"]),
        ("list",   ["list", "show my", "what stories", "all my stories"]),
        ("create", ["create", "new story", "start a", "make a"]),
    ],
    "chapter_mgmt": [
        ("delete",   ["delete chapter", "remove chapter", "delete this chapter", "delete the chapter"]),
        ("restore",  ["restore", "revert", "roll back", "previous version"]),
        ("versions", ["version history", "versions", "history of"]),
        ("open",     ["open chapter", "go to chapter", "switch to chapter", "show chapter"]),
        ("sync",     ["sync", "reindex", "re-index", "rebuild summaries"]),
        ("edit",     ["edit chapter", "update chapter", "overwrite chapter"]),
        ("create",   ["create", "add a chapter", "new chapter", "add chapter"]),
    ],
    "character_mgmt": [
        ("relationships", ["relationship between", "relationships of", "how are they related"]),
        ("graph",         ["character graph", "relationship map", "relationship graph"]),
        ("generate_cast", ["generate cast", "generate the cast", "detect characters", "auto-detect", "auto detect"]),
        ("search",        ["find", "where", "appears", "appear", "mentions", "scenes with", "search for"]),
        ("update",        ["update", "change the", "edit character"]),
        ("create",        ["create", "add a character", "new character"]),
    ],
    "text_transform": [
        ("translate", ["translate"]),
        ("age_adapt", ["young adult", "for children", "for kids", "for teens", " ya ", "age group"]),
        ("emotion",   ["emotion", "emotional", "darker", "sadder", "happier", "more fear", "more suspense", "tense", "scarier"]),
        ("style",     ["style", "gothic", "noir", "lyrical", "minimalist"]),
        ("tone",      ["tone", "mood", "lighter", "formal", "casual"]),
        ("refine",    ["refine", "polish", "improve", "clean up", "tighten"]),
    ],
    "search_replace": [
        ("replace",  ["replace", "swap", "change all", "rename the word", "find and replace"]),
        ("semantic", ["semantic", "similar passages", "by meaning", "scenes like"]),
        ("exact",    ["find all", "where", "appears", "appear", "search for", "scenes where", "mentions of"]),
    ],
    "story_intel": [
        ("dna",      ["dna", "essence", "core of the story"]),
        ("audience", ["audience", "readers", "who is it for"]),
        ("themes",   ["theme", "themes"]),
        ("genre",    ["genre"]),
        ("analyze",  ["analyze", "run intelligence", "intelligence"]),
    ],
    "intake_genre": [
        ("confirm", ["confirm"]),
        ("get",     ["what genre", "genre profile", "current genre"]),
        ("analyze", ["analyze", "detect the genre", "set up the story"]),
    ],
    "story_bible": [
        ("get",      ["show the bible", "show story bible", "existing bible", "what's in the bible"]),
        ("generate", ["generate", "create", "build", "make a"]),
    ],
    "pacing_goals": [
        ("set", ["set", "target", "goal of", "words per chapter of"]),
        ("get", ["what's my", "how am i", "show my pacing", "current pacing"]),
    ],
    "narrative_threads": [
        ("list", ["list", "show", "what threads", "unresolved"]),
        ("scan", ["scan", "track", "find threads"]),
    ],
}


def disambiguate_action(capability: str, command: str, llm_action: str) -> str:
    """Return the best action for `capability` given the command's verb cues.
    Falls back to the (valid) LLM action, else the first action."""
    cap = CAPABILITY_REGISTRY.get(capability)
    if not cap:
        return llm_action
    low = f" {command.lower()} "
    for action, cues in ACTION_CUES.get(capability, []):
        if action in cap.actions and any(c in low for c in cues):
            return action
    if llm_action in cap.actions:
        return llm_action
    return next(iter(cap.actions))


_CALLED_RE = _re.compile(r"\b(?:called|named|titled|entitled)\s+(.+)$", _re.IGNORECASE)


def extract_inline_params(capability: str, action: str, command: str) -> dict:
    """Cheap deterministic extraction of obvious params the LLM may miss
    (story/chapter title, character name)."""
    out: dict = {}
    m = _CALLED_RE.search(command.strip())
    if m:
        value = m.group(1).strip().strip('"\'.').strip()
        # drop a trailing genre word the title regex may swallow ("called X")
        if value:
            if capability == "project_mgmt" and action in ("create", "rename"):
                out["title"] = value
            elif capability == "character_mgmt" and action == "create":
                out["name"] = value
            elif capability == "chapter_mgmt" and action == "create":
                out["title"] = value
    return out
