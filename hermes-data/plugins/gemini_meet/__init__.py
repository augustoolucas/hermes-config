"""gemini_meet plugin — Google Meet with Gemini Live realtime voice.

Self-contained alternative to the bundled google_meet plugin.
Uses Gemini Live API instead of OpenAI Realtime for voice interaction.
"""

from __future__ import annotations


def register(ctx):
    """Register gemini_meet tools with Hermes."""
    import sys
    import os

    # Ensure the plugin's own directory is importable
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    from tools import (
        handle_gemini_meet_join,
        handle_gemini_meet_status,
        handle_gemini_meet_transcript,
        handle_gemini_meet_say,
        handle_gemini_meet_leave,
        GEMINI_MEET_JOIN_SCHEMA,
        GEMINI_MEET_STATUS_SCHEMA,
        GEMINI_MEET_TRANSCRIPT_SCHEMA,
        GEMINI_MEET_SAY_SCHEMA,
        GEMINI_MEET_LEAVE_SCHEMA,
    )

    ctx.register_tool(
        name="gemini_meet_join",
        description="Join a Google Meet call with Gemini Live realtime voice. "
        "The bot joins as a headless participant, transcribes captions, "
        "and can speak in the call via Gemini Live API.",
        parameters=GEMINI_MEET_JOIN_SCHEMA,
        handler=handle_gemini_meet_join,
    )
    ctx.register_tool(
        name="gemini_meet_status",
        description="Get the status of the current Gemini Meet session.",
        parameters=GEMINI_MEET_STATUS_SCHEMA,
        handler=handle_gemini_meet_status,
    )
    ctx.register_tool(
        name="gemini_meet_transcript",
        description="Read the transcript from the current or last Gemini Meet session.",
        parameters=GEMINI_MEET_TRANSCRIPT_SCHEMA,
        handler=handle_gemini_meet_transcript,
    )
    ctx.register_tool(
        name="gemini_meet_say",
        description="Speak text in an active Gemini Meet realtime session.",
        parameters=GEMINI_MEET_SAY_SCHEMA,
        handler=handle_gemini_meet_say,
    )
    ctx.register_tool(
        name="gemini_meet_leave",
        description="Leave the current Gemini Meet session.",
        parameters=GEMINI_MEET_LEAVE_SCHEMA,
        handler=handle_gemini_meet_leave,
    )
