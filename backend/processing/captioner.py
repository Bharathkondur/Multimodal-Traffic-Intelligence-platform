"""
Live scene captioning via a vision-language model.

The captioner consumes the current frame plus structured context
(detections + pose action labels) and returns a concise, grounded
description of what's happening. It's called on a cooldown by the
StreamProcessor (``caption_interval_s`` in settings) so we stay under
the VLM's rate ceiling and don't drown the UI in text.

Why hybrid input (frame + structured context) instead of just the frame?
    - Detections give the model exact counts, object classes, and track
      identities it would otherwise hallucinate or miss.
    - Pose action labels cheaply inject behavioural semantics the VLM
      would need a second pass to derive.
    - The VLM still gets the raw pixels, so spatial layout,
      texture, colour, and unknown-class objects (construction signage,
      trash, graffiti) are all still captured.

Provider abstraction:
    - ``GeminiCaptioner`` — Gemini 2.5 Flash (default).
    - ``NullCaptioner`` — safe no-op when no API key is present.
    - The base ``Captioner`` interface is a duck-type: implement
      ``async def caption(frame, detections, poses) -> dict | None``.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import google.generativeai as genai
    _GENAI = True
except ImportError:
    _GENAI = False


CAPTION_SYSTEM_PROMPT = """You are a live surveillance narrator.

Describe ONLY what is visibly happening in the frame RIGHT NOW, in one or
two short sentences (max 45 words). Ground every claim in either the
structured detection evidence provided or what is visually obvious. Do
not speculate about intent, identity, or prior events.

Output strict JSON with these keys:
{
  "summary": "<1 short sentence, present tense>",
  "caption": "<optional 2nd sentence with extra visible detail; may be empty>",
  "tags": ["<3-6 short keyword tags: e.g. 'traffic', 'pedestrian-crossing', 'stopped-vehicle'>"]
}

If the scene is empty or visually unreadable, return
{"summary": "Scene is empty.", "caption": "", "tags": []}.
"""


@dataclass
class CaptionResult:
    text: str
    summary: str
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "summary": self.summary, "tags": self.tags}


class NullCaptioner:
    """No-op fallback when a VLM isn't configured. Keeps the pipeline
    happy without crashing."""

    interval_s: float = 3.0

    async def caption(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return None


class GeminiCaptioner:
    """
    Gemini 2.5 Flash captioner.

    Uses the SDK's multimodal input with a compressed JPEG of the frame +
    a compact structured context blob. JSON mode keeps the output
    predictable; we still defensively parse because JSON mode isn't
    100% guaranteed.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        interval_s: float = 3.0,
        max_tokens: int = 160,
        frame_max_dim: int = 720,
        jpeg_quality: int = 70,
    ) -> None:
        if not _GENAI:
            raise RuntimeError(
                "google-generativeai not installed — pip install google-generativeai"
            )
        if not _CV2:
            raise RuntimeError("opencv-python required for frame encoding")
        if not api_key:
            raise ValueError("Gemini API key required")

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=CAPTION_SYSTEM_PROMPT,
        )
        self.model_name = model
        self.interval_s = float(interval_s)
        self.max_tokens = int(max_tokens)
        self.frame_max_dim = int(frame_max_dim)
        self.jpeg_quality = int(jpeg_quality)
        self._last_call_ts = 0.0

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    async def caption(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if frame is None or frame.size == 0:
            return None

        now = time.time()
        if (now - self._last_call_ts) < self.interval_s:
            return None
        self._last_call_ts = now

        try:
            img_bytes = self._encode_frame(frame)
            context = self._compact_context(detections, poses)

            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._generate_sync,
                img_bytes,
                context,
            )
            parsed = self._parse_response(response)
            if parsed is None:
                return None
            return parsed.to_dict()
        except Exception as e:
            logger.debug(f"GeminiCaptioner error: {e}")
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _encode_frame(self, frame: np.ndarray) -> bytes:
        h, w = frame.shape[:2]
        scale = self.frame_max_dim / max(h, w)
        if scale < 1.0:
            frame = cv2.resize(
                frame,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )
        ok, buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        )
        if not ok:
            raise RuntimeError("frame encoding failed")
        return bytes(buf)

    @staticmethod
    def _compact_context(
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
    ) -> str:
        """Collapse detections + poses into a compact, token-cheap blob."""
        # Class counts
        class_counts: Dict[str, int] = {}
        for d in detections:
            cls = (d.get("class_name") or d.get("type") or "object").lower()
            class_counts[cls] = class_counts.get(cls, 0) + 1

        # Action counts (from poses)
        action_counts: Dict[str, int] = {}
        for p in poses:
            a = (p.get("action") or "unknown").lower()
            if a and a != "unknown":
                action_counts[a] = action_counts.get(a, 0) + 1

        # Plates — include a few, cap for token safety
        plates = [d.get("plate_number") for d in detections if d.get("plate_number")]
        plates = plates[:5]

        context = {
            "class_counts": class_counts,
            "action_counts": action_counts,
            "plates_sample": plates,
            "total_detections": len(detections),
            "total_people_posed": len(poses),
        }
        return json.dumps(context, ensure_ascii=False)

    def _generate_sync(self, img_bytes: bytes, context_json: str) -> Any:
        """Blocking call — runs in executor."""
        return self._model.generate_content(
            [
                {
                    "role": "user",
                    "parts": [
                        {"text": (
                            "Describe the current frame. Ground your description "
                            "in this structured evidence from a CV pipeline.\n\n"
                            f"EVIDENCE:\n{context_json}"
                        )},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_bytes}},
                    ],
                }
            ],
            generation_config={
                "temperature": 0.35,
                "max_output_tokens": self.max_tokens,
                "response_mime_type": "application/json",
            },
        )

    @staticmethod
    def _parse_response(response: Any) -> Optional[CaptionResult]:
        """Parse Gemini JSON response; tolerate malformed output."""
        if response is None:
            return None
        text = getattr(response, "text", None)
        if not text:
            try:
                text = response.candidates[0].content.parts[0].text
            except Exception:
                return None
        if not text:
            return None

        cleaned = text.strip()
        # Strip markdown fences if the model added them despite JSON mode.
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            data = json.loads(cleaned)
        except Exception:
            # Last-chance: accept a bare summary string.
            return CaptionResult(text=cleaned[:240], summary=cleaned[:120], tags=[])

        summary = str(data.get("summary", "")).strip()
        caption = str(data.get("caption", "")).strip()
        tags_raw = data.get("tags", []) or []
        tags = [str(t).strip() for t in tags_raw if str(t).strip()][:6]

        combined = summary
        if caption:
            combined = f"{summary} {caption}".strip()
        if not combined:
            return None

        return CaptionResult(text=combined, summary=summary, tags=tags)


def build_captioner(settings: Any) -> Any:
    """Factory — picks a captioner based on settings."""
    if not getattr(settings, "captioning_enabled", True):
        return NullCaptioner()
    provider = getattr(settings, "llm_provider", "gemini").lower()
    if provider == "gemini":
        api_key = getattr(settings, "google_api_key", None)
        if not api_key:
            logger.warning("No GOOGLE_API_KEY — live captioning disabled")
            return NullCaptioner()
        try:
            return GeminiCaptioner(
                api_key=api_key,
                model=getattr(settings, "gemini_vision_model", "gemini-2.5-flash"),
                interval_s=getattr(settings, "caption_interval_s", 3.0),
                max_tokens=getattr(settings, "caption_max_tokens", 160),
            )
        except Exception as e:
            logger.warning(f"Captioner init failed ({e}) — disabled")
            return NullCaptioner()
    # Future: OpenAI / Ollama vision branches.
    return NullCaptioner()
