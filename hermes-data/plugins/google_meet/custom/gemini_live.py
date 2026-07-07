"""Gemini Live API adapter — same interface as RealtimeSession.

Drop-in replacement for plugins/google_meet/realtime/openai_client.py.
Connects to Gemini Live WebSocket, sends PCM16 16kHz audio, receives
PCM16 24kHz audio, appends to the same audio_sink_path.

Usage (same shape as RealtimeSession):
    sess = GeminiLiveSession(
        api_key=os.environ["GEMINI_API_KEY"],
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        voice="Puck",
        instructions="You are a helpful meeting assistant.",
        audio_sink_path=Path("speaker.pcm"),
        sample_rate=24000,
    )
    sess.connect()
    sess.speak("Hello team.")
    sess.close()
"""

from __future__ import annotations

import base64
import json
import time
import uuid
import threading
from pathlib import Path
from typing import Any, Callable, Optional


GEMINI_LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


def _require_websockets():
    try:
        from websockets.sync.client import connect as _connect  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "websockets package is required; "
            "install with: pip install websockets"
        ) from exc
    return _connect


class GeminiLiveSession:
    """Sync client for Gemini Live API, matching RealtimeSession's interface.

    Audio format bridge:
    - Input:  the caller sends PCM16 16kHz via send_audio()
    - Output: Gemini returns PCM16 24kHz → written to audio_sink_path
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-native-audio-preview-12-2025",
        voice: str = "Puck",
        instructions: str = "",
        audio_sink_path: Optional[Path] = None,
        sample_rate: int = 24000,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.audio_sink_path = Path(audio_sink_path) if audio_sink_path else None
        self.sample_rate = sample_rate
        self._ws: Any = None
        self._send_lock = threading.Lock()
        self.audio_bytes_out: int = 0
        self.last_audio_out_at: Optional[float] = None

    # ── lifecycle ───────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open WebSocket and send BidiGenerateContentSetup."""
        connect = _require_websockets()
        url = f"{GEMINI_LIVE_URL}?key={self.api_key}"

        try:
            self._ws = connect(url)
        except Exception:
            # Try with additional_headers for proxy compatibility
            self._ws = connect(url, additional_headers=[])

        config: dict[str, Any] = {
            "generation_config": {
                "response_modalities": ["AUDIO"],
            },
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": False,
                    "start_of_speech_sensitivity": 0.5,
                    "end_of_speech_sensitivity": 0.8,
                },
            },
        }
        if self.instructions:
            config["system_instruction"] = {
                "parts": [{"text": self.instructions}],
            }
        if self.voice:
            config["speech_config"] = {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": self.voice},
                }
            }

        setup = {
            "setup": config,
        }
        self._send_json(setup)

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── speaking ──────────────────────────────────────────────────────────

    def speak(self, text: str, timeout: float = 30.0) -> dict:
        """Send text and accumulate the audio response.

        Gemini Live processes realtime_input and streams back server_content.
        Audio parts are base64-decoded and appended to audio_sink_path.
        """
        if self._ws is None:
            raise RuntimeError("GeminiLiveSession.connect() must be called first")

        start = time.monotonic()

        # Send the text as realtime input
        self._send_json({
            "realtime_input": {
                "media_chunks": [{"text": text}],
            }
        })

        bytes_written = 0
        sink_fp = None
        if self.audio_sink_path is not None:
            self.audio_sink_path.parent.mkdir(parents=True, exist_ok=True)
            sink_fp = open(self.audio_sink_path, "ab")

        try:
            while True:
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError(
                        f"Gemini Live response did not complete within {timeout}s"
                    )
                raw = self._recv(timeout=remaining)
                if raw is None:
                    break
                msg = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
                if not isinstance(msg, dict):
                    continue

                # Check for server_content with audio
                sc = msg.get("serverContent") or {}
                model_turn = sc.get("modelTurn") or sc.get("model_turn") or {}
                parts = model_turn.get("parts", [])

                audio_received = False
                for part in parts:
                    inline = part.get("inlineData") or part.get("inline_data") or {}
                    data_b64 = inline.get("data", "")
                    mime = inline.get("mimeType", inline.get("mime_type", ""))
                    if data_b64 and "audio" in mime and sink_fp is not None:
                        try:
                            chunk = base64.b64decode(data_b64)
                        except (ValueError, TypeError):
                            chunk = b""
                        if chunk:
                            sink_fp.write(chunk)
                            sink_fp.flush()
                            bytes_written += len(chunk)
                            self.audio_bytes_out += len(chunk)
                            self.last_audio_out_at = time.time()
                            audio_received = True

                # Also check for text parts (transcription, debug)
                for part in parts:
                    if "text" in part:
                        pass  # Text transcription, not audio

                # Check for turn_complete
                if sc.get("turnComplete") or sc.get("turn_complete"):
                    break

                # Check for interruption
                if msg.get("interrupted"):
                    break

                # Setup complete message — not the end
                if msg.get("setupComplete"):
                    continue

        finally:
            if sink_fp is not None:
                sink_fp.close()

        duration_ms = (time.monotonic() - start) * 1000.0
        return {
            "ok": True,
            "bytes_written": bytes_written,
            "duration_ms": duration_ms,
        }

    # ── barge-in ──────────────────────────────────────────────────────────

    def cancel_response(self) -> bool:
        """Interrupt in-flight audio generation.

        Gemini Live doesn't have an explicit cancel, but closing and
        re-creating the WebSocket achieves the same effect. For now,
        we no-op — Gemini's automatic VAD handles barge-in natively.
        """
        return False

    # ── ws plumbing ───────────────────────────────────────────────────────

    def _send_json(self, payload: dict) -> None:
        assert self._ws is not None
        with self._send_lock:
            self._ws.send(json.dumps(payload))

    def _recv(self, timeout: Optional[float] = None):
        assert self._ws is not None
        try:
            if timeout is None:
                return self._ws.recv()
            return self._ws.recv(timeout=timeout)
        except TypeError:
            return self._ws.recv()
