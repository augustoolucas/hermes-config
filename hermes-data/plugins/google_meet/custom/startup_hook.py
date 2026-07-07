"""Startup hook: patch RealtimeSession when Gemini is configured.

Loaded via PYTHONSTARTUP env var. When HERMES_MEET_REALTIME_PROVIDER=gemini,
replaces RealtimeSession in the openai_client module with GeminiLiveSession.

Placement: /opt/data/profiles/accountability/custom_plugins/startup_hook.py
"""
import os
import sys

PROVIDER = os.environ.get("HERMES_MEET_REALTIME_PROVIDER", "").strip().lower()

if PROVIDER == "gemini":
    import plugins.google_meet.realtime.openai_client as _openai

    sys.path.insert(0, "/opt/data/profiles/accountability/custom_plugins")
    from gemini_live import GeminiLiveSession

    _openai.RealtimeSession = GeminiLiveSession
    sys.modules["plugins.google_meet.realtime.openai_client"].RealtimeSession = GeminiLiveSession
