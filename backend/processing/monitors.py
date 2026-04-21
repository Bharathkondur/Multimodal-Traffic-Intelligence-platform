"""
Rule engine + watchlist evaluator for Scene Intelligence.

A "rule" is a condition that should fire an alert when satisfied during
stream processing. Rules are authored in English by the user through the
watchlist panel, then compiled (best-effort) to structured predicates.
If compilation fails, the rule falls back to LLM-based evaluation at
much lower frequency.

Two predicate kinds supported natively:

    1. ``count``   — "if more than N <class> in <zone?> for >= T seconds"
    2. ``class``   — "when any <class> appears (in <zone?>)"
    3. ``action``  — "when person is <running|falling|fighting|...>"

Composite conditions are AND-ed.

The monitor:
    - Evaluates all active rules per frame (cheap — just dict lookups).
    - Applies per-rule cooldown so you don't spam the UI.
    - Captures a JPEG snapshot for each alert and hands it to the
      ``on_alert`` callback for persistence + broadcast.

Public entry point:  ``MonitorEngine.evaluate(...)`` returns alerts.
"""

from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False


# ----------------------------------------------------------------------
# Rule model
# ----------------------------------------------------------------------
ACTION_VOCAB = (
    "running", "falling", "lying_down", "hands_up", "sitting",
    "walking", "standing", "fighting",
)


@dataclass
class Rule:
    """A single user-authored alert rule."""
    id: str
    session_id: str
    name: str
    raw_text: str
    # Compiled predicate: dict with keys {kind, classes, action, min_count,
    # min_duration_s, zone_id}
    predicate: Optional[Dict[str, Any]] = None
    enabled: bool = True
    severity: str = "info"           # info | warning | critical
    cooldown_s: float = 15.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_text(cls, session_id: str, text: str, name: Optional[str] = None) -> "Rule":
        rule = cls(
            id=str(uuid.uuid4()),
            session_id=session_id,
            name=name or text.strip()[:60],
            raw_text=text,
        )
        rule.predicate = compile_rule(text)
        return rule


# ----------------------------------------------------------------------
# English → predicate compiler (best-effort regex, not magic)
# ----------------------------------------------------------------------
_COUNT_RE = re.compile(
    r"(?:more than|over|>=?|at least)\s+(\d+)\s+(\w[\w\s]*?)(?:\s+for\s+(\d+)\s*(s|sec|seconds|m|min|minutes)?)?",
    re.I,
)
_NEG_RE = re.compile(r"\bno\s+(\w[\w\s]*?)\b", re.I)
_APPEAR_RE = re.compile(r"\b(?:when|if|detect|alert\s+on)\b.*?\b(\w[\w\s]*?)\b", re.I)
_ACTION_RE = re.compile(
    r"\b(" + "|".join(ACTION_VOCAB) + r")\b", re.I
)
_ZONE_RE = re.compile(r"\bin\s+(?:zone\s+)?\"?([a-z0-9_\- ]+)\"?", re.I)


def _singularise(word: str) -> str:
    word = word.strip().lower()
    # A couple of common cases; good enough for the demo vocabulary.
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def compile_rule(text: str) -> Dict[str, Any]:
    """Produce a structured predicate from English text. Never raises."""
    text_norm = text.strip().lower()
    pred: Dict[str, Any] = {
        "kind": "appear",         # default
        "classes": [],
        "action": None,
        "min_count": 1,
        "min_duration_s": 0.0,
        "zone_id": None,
        "raw": text,
    }

    # Zone hint
    m = _ZONE_RE.search(text_norm)
    if m:
        pred["zone_id"] = m.group(1).strip().replace(" ", "_")

    # Action verbs override the default "appear" kind.
    m = _ACTION_RE.search(text_norm)
    if m:
        pred["kind"] = "action"
        pred["action"] = m.group(1).lower()
        pred["classes"] = ["person"]
        return pred

    # Count-based predicates
    m = _COUNT_RE.search(text_norm)
    if m:
        threshold = int(m.group(1))
        noun = _singularise(m.group(2))
        duration = 0.0
        if m.group(3):
            duration = float(m.group(3))
            unit = (m.group(4) or "s").lower()
            if unit.startswith("m"):
                duration *= 60
        pred["kind"] = "count"
        pred["classes"] = [noun]
        pred["min_count"] = threshold + 1  # "more than N" → ≥N+1
        pred["min_duration_s"] = duration
        return pred

    # "No person present" / "no vehicle in zone X"
    m = _NEG_RE.search(text_norm)
    if m:
        noun = _singularise(m.group(1))
        pred["kind"] = "absence"
        pred["classes"] = [noun]
        pred["min_duration_s"] = 5.0  # default
        return pred

    # Plain "appear" — find nouns that look like COCO classes.
    from detection.detector import COCO_CLASSES
    vocab = {v.lower() for v in COCO_CLASSES.values()}
    tokens = re.findall(r"[a-z]+", text_norm)
    found = [t for t in tokens if _singularise(t) in vocab]
    if found:
        pred["classes"] = [_singularise(found[0])]
    else:
        pred["classes"] = ["person"]  # safe default
    return pred


# ----------------------------------------------------------------------
# Monitor engine
# ----------------------------------------------------------------------
@dataclass
class _RuleState:
    rule: Rule
    last_alert_ts: float = 0.0
    # For count/absence: timestamp when the condition first started being true.
    condition_start_ts: Optional[float] = None


class MonitorEngine:
    """
    Evaluates active rules against per-frame detections + poses.

    Usage:
        engine = MonitorEngine()
        engine.add_rule(Rule.from_text(session_id, "alert when person falls"))
        alerts = await engine.evaluate(session_id=..., detections=..., poses=...)
    """

    def __init__(self) -> None:
        # session_id → list of rule states
        self._rules_by_session: Dict[str, List[_RuleState]] = {}
        # session_id → list of zone dicts {id, name, points: [[x,y], ...]}
        self._zones_by_session: Dict[str, List[Dict[str, Any]]] = {}

    # --- Rule management ------------------------------------------------
    def add_rule(self, rule: Rule) -> Rule:
        states = self._rules_by_session.setdefault(rule.session_id, [])
        states.append(_RuleState(rule=rule))
        logger.info(f"Rule added ({rule.session_id}): {rule.raw_text!r}")
        return rule

    def remove_rule(self, session_id: str, rule_id: str) -> bool:
        states = self._rules_by_session.get(session_id)
        if not states:
            return False
        before = len(states)
        self._rules_by_session[session_id] = [
            s for s in states if s.rule.id != rule_id
        ]
        return len(self._rules_by_session[session_id]) < before

    def list_rules(self, session_id: str) -> List[Rule]:
        return [s.rule for s in self._rules_by_session.get(session_id, [])]

    # --- Zone management ------------------------------------------------
    def set_zones(self, session_id: str, zones: List[Dict[str, Any]]) -> None:
        self._zones_by_session[session_id] = zones or []

    def list_zones(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._zones_by_session.get(session_id, []))

    # --- Evaluation -----------------------------------------------------
    async def evaluate(
        self,
        session_id: str,
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
        frame: Optional[np.ndarray] = None,
        timestamp: Optional[datetime] = None,
        frame_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        states = self._rules_by_session.get(session_id, [])
        if not states:
            return []

        zones = self._zones_by_session.get(session_id, [])
        zone_index = {z.get("id") or z.get("name"): z for z in zones}

        now = time.time()
        alerts: List[Dict[str, Any]] = []

        for state in states:
            rule = state.rule
            if not rule.enabled:
                continue
            pred = rule.predicate or {}

            # Scope objects by zone if the rule names one.
            zone = zone_index.get(pred.get("zone_id")) if pred.get("zone_id") else None

            def _in_scope(det: Dict[str, Any]) -> bool:
                if zone is None:
                    return True
                bbox = det.get("bbox")
                if not bbox or len(bbox) != 4:
                    return False
                cx = (bbox[0] + bbox[2]) / 2.0
                cy = (bbox[1] + bbox[3]) / 2.0
                return _point_in_polygon(cx, cy, zone.get("points") or [])

            matched = False
            matched_objects: List[Dict[str, Any]] = []
            reason = ""

            kind = pred.get("kind")
            target_classes = {c.lower() for c in pred.get("classes") or []}

            if kind == "count":
                count = sum(
                    1 for d in detections
                    if (d.get("class_name") or d.get("type") or "").lower() in target_classes
                    and _in_scope(d)
                )
                threshold = pred.get("min_count", 1)
                duration = pred.get("min_duration_s", 0.0)
                if count >= threshold:
                    if state.condition_start_ts is None:
                        state.condition_start_ts = now
                    if (now - state.condition_start_ts) >= duration:
                        matched = True
                        reason = f"{count} × {','.join(target_classes)} (threshold {threshold})"
                        matched_objects = [
                            d for d in detections
                            if (d.get("class_name") or d.get("type") or "").lower() in target_classes
                            and _in_scope(d)
                        ]
                else:
                    state.condition_start_ts = None

            elif kind == "action":
                action = pred.get("action")
                for p in poses:
                    if p.get("action") == action:
                        # Optional: verify action person is in zone.
                        if zone is not None:
                            bbox = p.get("bbox")
                            if not bbox or len(bbox) != 4:
                                continue
                            cx = (bbox[0] + bbox[2]) / 2.0
                            cy = (bbox[1] + bbox[3]) / 2.0
                            if not _point_in_polygon(cx, cy, zone.get("points") or []):
                                continue
                        matched = True
                        reason = f"person detected performing: {action}"
                        matched_objects.append({
                            "bbox": list(p.get("bbox") or []),
                            "track_id": p.get("track_id"),
                            "action": action,
                            "class_name": "person",
                        })

            elif kind == "appear":
                for d in detections:
                    cls = (d.get("class_name") or d.get("type") or "").lower()
                    if cls in target_classes and _in_scope(d):
                        matched = True
                        reason = f"{cls} detected"
                        matched_objects.append(d)
                        break

            elif kind == "absence":
                count = sum(
                    1 for d in detections
                    if (d.get("class_name") or d.get("type") or "").lower() in target_classes
                    and _in_scope(d)
                )
                if count == 0:
                    if state.condition_start_ts is None:
                        state.condition_start_ts = now
                    if (now - state.condition_start_ts) >= pred.get("min_duration_s", 5.0):
                        matched = True
                        reason = f"no {','.join(target_classes)} visible"
                else:
                    state.condition_start_ts = None

            if not matched:
                continue

            # Cooldown
            if (now - state.last_alert_ts) < rule.cooldown_s:
                continue
            state.last_alert_ts = now

            alert = {
                "alert_id": str(uuid.uuid4()),
                "rule_id": rule.id,
                "rule_name": rule.name,
                "session_id": session_id,
                "severity": rule.severity,
                "reason": reason,
                "matched_objects": matched_objects[:10],
                "zone_id": pred.get("zone_id"),
                "frame_id": frame_id,
                "timestamp": (timestamp or datetime.utcnow()).isoformat(),
                "snapshot_b64": self._capture_snapshot(frame) if frame is not None else None,
            }
            alerts.append(alert)
            logger.info(
                f"ALERT [{rule.name}] → {reason} "
                f"(session={session_id}, frame={frame_id})"
            )
        return alerts

    @staticmethod
    def _capture_snapshot(
        frame: np.ndarray,
        max_dim: int = 960,
        quality: int = 70,
    ) -> Optional[str]:
        if not _CV2 or frame is None or frame.size == 0:
            return None
        try:
            h, w = frame.shape[:2]
            scale = max_dim / max(h, w)
            if scale < 1.0:
                frame = cv2.resize(
                    frame,
                    (int(w * scale), int(h * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
            )
            if not ok:
                return None
            return base64.b64encode(buf).decode("utf-8")
        except Exception:
            return None


# ----------------------------------------------------------------------
# Geometry — point-in-polygon (ray casting)
# ----------------------------------------------------------------------
def _point_in_polygon(x: float, y: float, polygon: List[List[float]]) -> bool:
    if not polygon or len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


# ----------------------------------------------------------------------
# Seeded demo rules — 4 canonical scenarios for the demo
# ----------------------------------------------------------------------
DEMO_RULES = [
    {
        "name": "Loitering person",
        "text": "alert when more than 2 persons for 30 seconds",
        "severity": "warning",
    },
    {
        "name": "Person falling",
        "text": "alert when a person falling",
        "severity": "critical",
    },
    {
        "name": "Stopped vehicle",
        "text": "alert when more than 1 car for 20 seconds",
        "severity": "warning",
    },
    {
        "name": "Unattended bag",
        "text": "alert when a backpack appears",
        "severity": "info",
    },
]


def seed_demo_rules(engine: MonitorEngine, session_id: str) -> List[Rule]:
    """Attach the 4 canonical demo rules to a session on startup."""
    created: List[Rule] = []
    for r in DEMO_RULES:
        rule = Rule.from_text(session_id, r["text"], name=r["name"])
        rule.severity = r["severity"]
        engine.add_rule(rule)
        created.append(rule)
    return created
