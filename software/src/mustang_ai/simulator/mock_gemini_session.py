"""Deterministic `MockGeminiLiveSession` satisfying `GeminiLiveSessionProtocol` using `google-genai>=2.34.0` types."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from google.genai import types

from mustang_ai.config import GeminiERConfig
from mustang_ai.protocol.messages import GeminiStreamEvent
from mustang_ai.runtime.gemini_live_stream import build_gemini_live_connect_config


class MockGeminiLiveSession:
    """Scriptable mock session for `gemini-robotics-er-2-streaming` validating `google.genai.types` wire payloads."""

    def __init__(self, config: GeminiERConfig | None = None) -> None:
        self.config = config or GeminiERConfig()
        self.live_connect_config: types.LiveConnectConfig = build_gemini_live_connect_config(self.config)
        self._event_queue: list[GeminiStreamEvent] = []
        self.received_video_jpegs: list[bytes] = []
        self.received_audio_pcm16: list[bytes] = []
        self.received_video_blobs: list[types.Blob] = []
        self.received_audio_blobs: list[types.Blob] = []
        self.emitted_function_calls: list[types.FunctionCall] = []
        self.received_tool_responses: list[dict[str, Any]] = []
        self.received_genai_function_responses: list[types.FunctionResponse] = []

    def enqueue_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        call_id: str | None = None,
    ) -> types.FunctionCall:
        cid = call_id or f"call_{len(self.emitted_function_calls) + 1}"
        fc = types.FunctionCall(id=cid, name=tool_name, args=dict(tool_args))
        self.emitted_function_calls.append(fc)
        self._event_queue.append(
            GeminiStreamEvent(
                timestamp_s=time.monotonic(),
                event_type="tool_call",
                tool_name=fc.name or tool_name,
                tool_call_id=fc.id or cid,
                tool_args=dict(fc.args or {}),
            )
        )
        return fc

    def enqueue_disconnect(self) -> None:
        self._event_queue.append(
            GeminiStreamEvent(
                timestamp_s=time.monotonic(),
                event_type="disconnect",
            )
        )

    async def send_video_jpeg(self, jpeg_bytes: bytes) -> None:
        blob = types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
        self.received_video_blobs.append(blob)
        self.received_video_jpegs.append(jpeg_bytes)

    async def send_audio_pcm16(self, pcm16_bytes: bytes) -> None:
        blob = types.Blob(data=pcm16_bytes, mime_type="audio/pcm;rate=16000")
        self.received_audio_blobs.append(blob)
        self.received_audio_pcm16.append(pcm16_bytes)

    async def receive_events(self) -> AsyncIterator[GeminiStreamEvent]:
        while self._event_queue:
            ev = self._event_queue.pop(0)
            yield ev

    async def send_tool_response(self, call_id: str, tool_name: str, result: dict[str, object]) -> None:
        fn_resp = types.FunctionResponse(
            id=call_id,
            name=tool_name,
            response={**result, "scheduling": "SILENT"},
        )
        self.received_genai_function_responses.append(fn_resp)
        self.received_tool_responses.append(
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "result": dict(result),
            }
        )
