"""
NarratIQ Real-Time Voice Agent — service package.

Pipeline (see services/voice/agent.py for the orchestrating facade):

  audio → stt_stream → normalize → session_memory → reference
        → intent → capabilities → planner → context → safety
        → orchestrator → (consolidated VoiceAgentResponse) → analytics

All routing is data-driven:
  - capabilities.CAPABILITY_REGISTRY  : authoritative capability specs (C)
  - catalog.FEATURE_CATALOG           : phrases for BGE-M3 shortlist
  - catalog.INTENT_REGISTRY           : intent → (capability, action)

Adding a feature/plugin = adding registry rows; no control-flow changes.
"""
