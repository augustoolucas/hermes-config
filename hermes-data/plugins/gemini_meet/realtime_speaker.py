"""RealtimeSpeaker — file-based JSONL queue wrapper for any RealtimeSession.

Extracted from plugins/google_meet/realtime/openai_client.py so the
gemini_meet plugin can use it without importing the OpenAI client.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional


class RealtimeSpeaker:
    """File-based JSONL queue wrapper around a RealtimeSession.

    Each line in ``queue_path`` is a JSON object of the form
    ``{"id": "<uuid>", "text": "..."}``. Processed lines are appended
    to ``processed_path`` (if set) and then removed from the queue;
    if ``processed_path`` is ``None``, processed lines are simply
    dropped.
    """

    def __init__(
        self,
        session: Any,
        queue_path: Path,
        processed_path: Optional[Path] = None,
    ) -> None:
        self.session = session
        self.queue_path = Path(queue_path)
        self.processed_path = Path(processed_path) if processed_path else None

    # ── helpers ──────────────────────────────────────────────────────────

    def _read_queue(self) -> list[dict]:
        if not self.queue_path.exists():
            return []
        out: list[dict] = []
        for line in self.queue_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if "id" not in entry:
                entry["id"] = str(uuid.uuid4())
            out.append(entry)
        return out

    def _rewrite_queue(self, remaining: list[dict]) -> None:
        if not remaining:
            self.queue_path.write_text("")
            return
        self.queue_path.write_text(
            "\n".join(json.dumps(e) for e in remaining) + "\n"
        )

    def _append_processed(self, entry: dict, result: dict) -> None:
        if self.processed_path is None:
            return
        self.processed_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"id": entry.get("id"), "text": entry.get("text", ""), "result": result}
        with open(self.processed_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(record) + "\n")

    # ── main loop ────────────────────────────────────────────────────────

    def run_until_stopped(
        self,
        stop_fn: Callable[[], bool],
        poll_interval: float = 0.5,
    ) -> None:
        while not stop_fn():
            entries = self._read_queue()
            if not entries:
                time.sleep(poll_interval)
                continue
            head = entries[0]
            text = (head.get("text") or "").strip()
            if text:
                try:
                    result = self.session.speak(text)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
            else:
                result = {"ok": True, "bytes_written": 0, "duration_ms": 0.0}
            self._append_processed(head, result)

            latest = self._read_queue()
            if latest and latest[0].get("id") == head.get("id"):
                self._rewrite_queue(latest[1:])
            else:
                self._rewrite_queue(
                    [e for e in latest if e.get("id") != head.get("id")]
                )
