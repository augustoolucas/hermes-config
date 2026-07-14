import logging

logger = logging.getLogger(__name__)


def register(api):
    from hermes_plugins.accountability_tools.tools import (
        handle_daily_summary_load,
        handle_daily_summary_save,
        handle_focus_session_start,
        handle_focus_session_complete,
        handle_checkin_state_update,
        handle_focus_session_status,
    )

    api.register_tool(
        name="daily_summary_load",
        handler=handle_daily_summary_load,
        toolset="accountability-tools",
        schema={
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format. If empty, loads today's.",
            }
        },
    )

    api.register_tool(
        name="daily_summary_save",
        handler=handle_daily_summary_save,
        toolset="accountability-tools",
        schema={
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format. Use today's date.",
            },
            "summary_text": {
                "type": "string",
                "description": "Brief summary of today's activities (1-3 sentences).",
            },
            "context": {
                "type": "string",
                "description": "Broader context — day of week, what Lucas was doing this week, etc.",
            },
            "intention": {
                "type": "string",
                "description": "Main intention for the day, extracted from W1 response. One short sentence.",
            },
            "plans_for_next_day": {
                "type": "string",
                "description": "What Lucas plans to start with tomorrow. One short sentence.",
            },
            "tasks": {
                "type": "array",
                "description": "List of task objects with id, name, status, notes, since/completed fields.",
            },
            "metrics": {
                "type": "object",
                "description": "Gamification metrics: tasks_completed_today, focus_sessions_completed, focus_minutes_total, checkins_responded, checkins_total, current_streak.",
            },
        },
    )

    api.register_tool(
        name="focus_session_start",
        handler=handle_focus_session_start,
        toolset="accountability-tools",
        schema={
            "task_name": {
                "type": "string",
                "description": "Name of the task Lucas is focusing on.",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Planned duration in minutes (e.g., 25, 60, 90).",
            },
        },
    )

    api.register_tool(
        name="focus_session_complete",
        handler=handle_focus_session_complete,
        toolset="accountability-tools",
        schema={
            "session_id": {
                "type": "string",
                "description": "ID of the focus session to complete.",
            },
            "result": {
                "type": "string",
                "description": "Brief result/note about what was accomplished (optional).",
            },
        },
    )

    api.register_tool(
        name="checkin_state_update",
        handler=handle_checkin_state_update,
        toolset="accountability-tools",
        schema={
            "window": {
                "type": "string",
                "description": "Check-in window: '1', '2', or '3'.",
            },
            "field": {
                "type": "string",
                "description": "Field to update: checkin_sent_at, user_responded_at, followup_action, followup_sent_at, escalation_sent.",
            },
            "value": {
                "type": "string",
                "description": "Value to set. Use integer epoch for _at fields, string for action fields.",
            },
        },
    )

    api.register_tool(
        name="focus_session_status",
        handler=handle_focus_session_status,
        toolset="accountability-tools",
        schema={
            "session_id": {
                "type": "string",
                "description": "Optional. Session ID to check. If empty, returns active session status.",
            },
        },
    )

    logger.info("accountability-tools: 6 tools registered")
