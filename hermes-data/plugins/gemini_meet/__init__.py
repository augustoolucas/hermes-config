"""gemini_meet plugin — Google Meet with Gemini Live realtime voice.

Self-contained alternative to the bundled google_meet plugin.
Uses Gemini Live API instead of OpenAI Realtime for voice interaction.
"""

from __future__ import annotations


def register(ctx):
    """Register gemini_meet tools with Hermes."""
    import sys
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Import using the full module path to avoid conflicts with Hermes' own tools/ module
    from hermes_plugins.gemini_meet.tools import (
        handle_gemini_meet_join,
        handle_gemini_meet_status,
        handle_gemini_meet_transcript,
        handle_gemini_meet_say,
        handle_gemini_meet_leave,
        handle_gemini_meet_create,
        GEMINI_MEET_JOIN_SCHEMA,
        GEMINI_MEET_STATUS_SCHEMA,
        GEMINI_MEET_TRANSCRIPT_SCHEMA,
        GEMINI_MEET_SAY_SCHEMA,
        GEMINI_MEET_LEAVE_SCHEMA,
        GEMINI_MEET_CREATE_SCHEMA,
    )

    ctx.register_tool(
        name="gemini_meet_join",
        toolset="gemini_meet",
        description="Join a Google Meet call with Gemini Live realtime voice. "
        "The bot joins as a headless participant, transcribes captions, "
        "and can speak in the call via Gemini Live API.",
        schema=GEMINI_MEET_JOIN_SCHEMA,
        handler=handle_gemini_meet_join,
    )
    ctx.register_tool(
        name="gemini_meet_status",
        toolset="gemini_meet",
        description="Get the status of the current Gemini Meet session.",
        schema=GEMINI_MEET_STATUS_SCHEMA,
        handler=handle_gemini_meet_status,
    )
    ctx.register_tool(
        name="gemini_meet_transcript",
        toolset="gemini_meet",
        description="Read the transcript from the current or last Gemini Meet session.",
        schema=GEMINI_MEET_TRANSCRIPT_SCHEMA,
        handler=handle_gemini_meet_transcript,
    )
    ctx.register_tool(
        name="gemini_meet_say",
        toolset="gemini_meet",
        description="Speak text in an active Gemini Meet realtime session.",
        schema=GEMINI_MEET_SAY_SCHEMA,
        handler=handle_gemini_meet_say,
    )
    ctx.register_tool(
        name="gemini_meet_leave",
        toolset="gemini_meet",
        description="Leave the current Gemini Meet session.",
        schema=GEMINI_MEET_LEAVE_SCHEMA,
        handler=handle_gemini_meet_leave,
    )
    ctx.register_tool(
        name="gemini_meet_create",
        toolset="gemini_meet",
        description="Create a Google Calendar event with a Google Meet conference link. "
        "Returns the Meet URL, ready for gemini_meet_join. "
        "Uses the Google OAuth token already configured on this profile.",
        schema=GEMINI_MEET_CREATE_SCHEMA,
        handler=handle_gemini_meet_create,
    )
