"""
Behavior detector — the Scene-Intelligence-era replacement for the
vehicle-only incident detector.

This module is intentionally thin: behaviour detection now lives in
``processing.monitors.MonitorEngine`` because the same logic powers
user-authored watchlist rules. ``BehaviorDetector`` is a small façade
that:

    1. Owns a ``MonitorEngine`` instance.
    2. Pre-seeds a baseline set of "obvious" behavioural rules that
       customers expect out of the box (falling, loitering, intrusion).
    3. Maps the engine's alert dicts to the legacy ``incident`` shape
       so existing DB schemas, websocket consumers, and Grafana panels
       keep working without conditional code.

The original ``IncidentDetector`` (traffic-only stopped/wrong-way
heuristics) is still available for callers that only need the
traffic incident path.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from processing.monitors import (
    DEMO_RULES,
    MonitorEngine,
    Rule,
    seed_demo_rules,
)

logger = logging.getLogger(__name__)


# Map our generic behaviour kinds to the legacy incident vocabulary so
# existing DB tables (incident_type) and dashboards keep working.
_BEHAVIOR_TO_INCIDENT_TYPE = {
    "action:falling": "person_fall",
    "action:fighting": "altercation",
    "action:running": "running_person",
    "action:hands_up": "distress_signal",
    "appear:backpack": "unattended_bag",
    "appear:suitcase": "unattended_bag",
    "count:car": "vehicle_congestion",
    "count:person": "crowd_gathering",
    "absence:person": "abandoned_area",
    "default": "behavior_event",
}

_SEVERITY_MAP = {
    "info": "low",
    "warning": "medium",
    "critical": "high",
}


class BehaviorDetector:
    """Façade over MonitorEngine that emits legacy-compatible incident dicts."""

    def __init__(self, monitor: Optional[MonitorEngine] = None) -> None:
        self.monitor = monitor or MonitorEngine()

    # --- Lifecycle ------------------------------------------------------
    def attach_session(
        self,
        session_id: str,
        seed_defaults: bool = True,
    ) -> List[Rule]:
        """Bind the detector to a session and optionally seed demo rules."""
        if seed_defaults:
            return seed_demo_rules(self.monitor, session_id)
        return []

    # --- Detection ------------------------------------------------------
    async def detect(
        self,
        session_id: str,
        detections: List[Dict[str, Any]],
        poses: List[Dict[str, Any]],
        frame: Optional[np.ndarray] = None,
        frame_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Run all rules and return alerts shaped as legacy 'incidents'."""
        alerts = await self.monitor.evaluate(
            session_id=session_id,
            detections=detections,
            poses=poses,
            frame=frame,
            frame_id=frame_id,
            timestamp=timestamp,
        )
        return [self._to_incident(a) for a in alerts]

    # --- Translation ----------------------------------------------------
    @staticmethod
    def _to_incident(alert: Dict[str, Any]) -> Dict[str, Any]:
        """Map a MonitorEngine alert → legacy incident dict."""
        kind_key = "default"
        # Reconstruct the lookup key from the rule's predicate hints in
        # the alert (we kept matched_objects so this is cheap).
        first = (alert.get("matched_objects") or [{}])[0]
        action = first.get("action")
        cls = (first.get("class_name") or first.get("type") or "").lower()
        if action:
            kind_key = f"action:{action}"
        elif cls:
            # Heuristically choose between appear:, count:, absence: by
            # parsing the reason string. Defaults are fine if it doesn't match.
            reason = (alert.get("reason") or "").lower()
            if "no " in reason and "visible" in reason:
                kind_key = f"absence:{cls}"
            elif "threshold" in reason:
                kind_key = f"count:{cls}"
            else:
                kind_key = f"appear:{cls}"

        incident_type = _BEHAVIOR_TO_INCIDENT_TYPE.get(kind_key, _BEHAVIOR_TO_INCIDENT_TYPE["default"])

        # Choose a representative location (centroid of first matched object)
        location = None
        bbox = first.get("bbox")
        if bbox and len(bbox) == 4:
            location = {
                "x": (bbox[0] + bbox[2]) / 2.0,
                "y": (bbox[1] + bbox[3]) / 2.0,
            }

        return {
            "incident_id": alert.get("alert_id"),
            "incident_type": incident_type,
            "severity": _SEVERITY_MAP.get(alert.get("severity", "info"), "low"),
            "description": f"{alert.get('rule_name')} — {alert.get('reason')}",
            "rule_name": alert.get("rule_name"),
            "rule_id": alert.get("rule_id"),
            "session_id": alert.get("session_id"),
            "location": location,
            "involved_tracks": [
                obj.get("track_id") for obj in alert.get("matched_objects") or []
                if obj.get("track_id") is not None
            ],
            "frame_id": alert.get("frame_id"),
            "timestamp": alert.get("timestamp"),
            "snapshot_b64": alert.get("snapshot_b64"),
            "is_active": True,
        }
