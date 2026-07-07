"""sitecustomize — auto-loaded for ALL Python invocations (incl. subprocesses).

When HERMES_MEET_REALTIME_PROVIDER=gemini is set, replaces RealtimeSession
in the openai_client module with GeminiLiveSession so meet_bot uses Gemini
Live API instead of OpenAI Realtime for realtime Meet voice.

Placed in the venv site-packages by deploy.sh.
"""
import os
import sys

_provider = os.environ.get("HERMES_MEET_REALTIME_PROVIDER", "").strip().lower()

if _provider == "gemini":
    _custom_dir = os.environ.get(
        "HERMES_MEET_CUSTOM_DIR",
        "/opt/data/profiles/accountability/custom_plugins",
    )
    sys.path.insert(0, _custom_dir)

    from gemini_live import GeminiLiveSession  # noqa: E402

    import plugins.google_meet.realtime.openai_client as _openai  # noqa: E402

    _openai.RealtimeSession = GeminiLiveSession  # type: ignore[attr-defined]
    sys.modules["plugins.google_meet.realtime.openai_client"].RealtimeSession = (
        GeminiLiveSession  # type: ignore[attr-defined]
    )
