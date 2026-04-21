"""
YOLO26-pose estimation + rule-based action classification.

Emits 17-keypoint COCO skeletons per person and derives a coarse action
label (standing / sitting / walking / running / falling / lying / raising-hands)
using simple geometric heuristics. No extra ML models — just a couple of
angles and aspect-ratio checks. This is deliberately minimal: we want a
signal that's useful for watchlist rules without paying for an LSTM.

Keypoint indices (COCO-17):
    0 nose              1 left_eye         2 right_eye
    3 left_ear          4 right_ear
    5 left_shoulder     6 right_shoulder
    7 left_elbow        8 right_elbow
    9 left_wrist       10 right_wrist
   11 left_hip         12 right_hip
   13 left_knee        14 right_knee
   15 left_ankle       16 right_ankle
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False


# Confidence thresholds for body parts to be considered "seen".
_KP_VISIBILITY_THRESHOLD = 0.3


@dataclass
class PersonPose:
    """One person's pose + derived action label for a single frame."""
    track_id: Optional[int]
    bbox: Tuple[float, float, float, float]
    keypoints: List[List[float]]  # [[x, y, conf], ...] length 17
    action: str = "unknown"
    action_confidence: float = 0.0
    # Optional motion-based attributes, filled by PoseActionClassifier
    speed_px_s: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "track_id": self.track_id,
            "bbox": list(self.bbox),
            "keypoints": self.keypoints,
            "action": self.action,
            "action_confidence": self.action_confidence,
            "speed_px_s": self.speed_px_s,
        }


class PoseEstimator:
    """Thin wrapper around ultralytics YOLO-pose with graceful fallback."""

    def __init__(
        self,
        model_path: str = "yolo26s-pose.pt",
        confidence_threshold: float = 0.35,
        device: Optional[str] = None,
    ) -> None:
        if not YOLO_AVAILABLE:
            raise RuntimeError("ultralytics not installed — pip install ultralytics")

        self.confidence_threshold = confidence_threshold

        # Auto-detect device
        if device is None:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        self.device = device

        # Fallback chain keeps the stage useful even if YOLO26 weights aren't cached.
        fallback = [model_path, "yolo11s-pose.pt", "yolov8s-pose.pt"]
        last_err: Optional[Exception] = None
        self.model = None
        for cand in fallback:
            try:
                self.model = YOLO(cand)
                self.model.to(device)
                self.model_path = cand
                if cand != model_path:
                    logger.warning(
                        f"Pose model '{model_path}' unavailable; using '{cand}'"
                    )
                break
            except Exception as e:  # pragma: no cover
                last_err = e
        if self.model is None:
            raise RuntimeError(f"Failed to load any pose model: {last_err}")

        logger.info(f"Pose model loaded: {self.model_path} on {device}")

    def estimate(
        self,
        frame: np.ndarray,
        max_persons: int = 20,
    ) -> List[PersonPose]:
        """Return a list of PersonPose objects for this frame."""
        if frame is None or frame.size == 0:
            return []

        try:
            results = self.model(frame, conf=self.confidence_threshold, verbose=False)
        except Exception as e:
            logger.debug(f"Pose inference failed: {e}")
            return []

        poses: List[PersonPose] = []
        if not results:
            return poses

        result = results[0]
        if result.keypoints is None or result.boxes is None:
            return poses

        kps_tensor = result.keypoints.data  # shape (N, 17, 3) — (x, y, conf)
        boxes_tensor = result.boxes.xyxy    # shape (N, 4)

        try:
            kps_np = kps_tensor.cpu().numpy()
            boxes_np = boxes_tensor.cpu().numpy()
        except AttributeError:
            kps_np = np.asarray(kps_tensor)
            boxes_np = np.asarray(boxes_tensor)

        for i in range(min(len(kps_np), max_persons)):
            kp_arr = kps_np[i].tolist()
            x1, y1, x2, y2 = (float(v) for v in boxes_np[i])
            poses.append(
                PersonPose(
                    track_id=None,
                    bbox=(x1, y1, x2, y2),
                    keypoints=[[float(x), float(y), float(c)] for x, y, c in kp_arr],
                )
            )

        return poses


class PoseActionClassifier:
    """
    Heuristic action classifier over a short motion window per track.

    Stores recent centroids to estimate speed in pixels/second. Each call
    returns (action, confidence). Actions are a small ontology chosen to
    match common surveillance use cases — not a full HAR taxonomy.
    """

    ACTIONS = (
        "standing",
        "sitting",
        "walking",
        "running",
        "falling",
        "lying_down",
        "hands_up",
        "unknown",
    )

    def __init__(self, history_seconds: float = 1.5) -> None:
        self._history_seconds = history_seconds
        # track_id → list of (t, cx, cy)
        self._motion: Dict[int, List[Tuple[float, float, float]]] = {}

    def update_and_classify(
        self,
        person: PersonPose,
        track_id: Optional[int],
        now: Optional[float] = None,
    ) -> PersonPose:
        now = now if now is not None else time.time()
        person.track_id = track_id

        # --- 1. Motion speed ------------------------------------------------
        if track_id is not None:
            cx = (person.bbox[0] + person.bbox[2]) / 2.0
            cy = (person.bbox[1] + person.bbox[3]) / 2.0
            history = self._motion.setdefault(track_id, [])
            history.append((now, cx, cy))
            # Prune old samples
            cutoff = now - self._history_seconds
            while history and history[0][0] < cutoff:
                history.pop(0)

            if len(history) >= 2:
                t0, x0, y0 = history[0]
                tn, xn, yn = history[-1]
                dt = tn - t0
                if dt > 0:
                    dist = math.hypot(xn - x0, yn - y0)
                    person.speed_px_s = dist / dt

        # --- 2. Pose geometry -----------------------------------------------
        action, conf = self._classify_geometry(person)

        # --- 3. Motion-aware overrides --------------------------------------
        # If the body is upright-ish but moving fast → walking / running.
        if action in ("standing", "unknown"):
            if person.speed_px_s > 220:
                action, conf = "running", max(conf, 0.7)
            elif person.speed_px_s > 55:
                action, conf = "walking", max(conf, 0.65)

        person.action = action
        person.action_confidence = conf
        return person

    # ------------------------------------------------------------------
    # Geometric primitives
    # ------------------------------------------------------------------
    @staticmethod
    def _kp(person: PersonPose, idx: int) -> Optional[Tuple[float, float]]:
        kps = person.keypoints
        if idx >= len(kps):
            return None
        x, y, c = kps[idx]
        if c < _KP_VISIBILITY_THRESHOLD:
            return None
        return (x, y)

    def _classify_geometry(self, person: PersonPose) -> Tuple[str, float]:
        """Return (action_label, confidence) using pose-only heuristics."""
        left_shoulder = self._kp(person, 5)
        right_shoulder = self._kp(person, 6)
        left_hip = self._kp(person, 11)
        right_hip = self._kp(person, 12)
        left_knee = self._kp(person, 13)
        right_knee = self._kp(person, 14)
        left_ankle = self._kp(person, 15)
        right_ankle = self._kp(person, 16)
        left_wrist = self._kp(person, 9)
        right_wrist = self._kp(person, 10)
        nose = self._kp(person, 0)

        # Midpoints
        shoulder = _avg(left_shoulder, right_shoulder)
        hip = _avg(left_hip, right_hip)
        knee = _avg(left_knee, right_knee)
        ankle = _avg(left_ankle, right_ankle)

        # Hands up: both wrists above shoulders, visible.
        if (
            nose
            and left_wrist and right_wrist
            and shoulder
            and left_wrist[1] < shoulder[1]
            and right_wrist[1] < shoulder[1]
        ):
            return "hands_up", 0.75

        # Body aspect — lying detection from bbox.
        x1, y1, x2, y2 = person.bbox
        w = max(x2 - x1, 1.0)
        h = max(y2 - y1, 1.0)
        aspect = h / w  # tall = upright, short = horizontal

        if aspect < 0.55:
            # Much wider than tall — probably lying down.
            return "lying_down", 0.8

        # Need shoulder + hip visible for next heuristics.
        if not shoulder or not hip:
            return "unknown", 0.25

        torso_vec = (hip[0] - shoulder[0], hip[1] - shoulder[1])
        torso_angle_deg = math.degrees(math.atan2(torso_vec[0], torso_vec[1]))
        # Upright → angle near 0°; horizontal → near ±90°.

        if abs(torso_angle_deg) > 55:
            # Torso horizontal but bbox wasn't flat enough for "lying".
            # Treat a steep-angle torso as a fall in progress.
            return "falling", 0.6

        # Sitting: hips and knees roughly at the same y, ankles below or
        # missing (thighs horizontal).
        if hip and knee:
            hip_knee_dy = abs(hip[1] - knee[1])
            hip_knee_dx = abs(hip[0] - knee[0])
            if hip_knee_dy < hip_knee_dx * 0.5 and aspect < 1.5:
                return "sitting", 0.65

        # Standing: upright torso, ankles below hips, bbox tall.
        if ankle and hip and ankle[1] > hip[1] and aspect > 1.4:
            return "standing", 0.6

        return "standing", 0.4  # generic fallback for upright people


def _avg(
    p1: Optional[Tuple[float, float]],
    p2: Optional[Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    if p1 and p2:
        return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    return p1 or p2
