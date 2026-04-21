"""
YOLO-based universal scene detection module.

Supports YOLO26 (2026), YOLO11, and legacy YOLOv8 via the shared Ultralytics
API. Detects all 80 COCO classes by default; callers can opt-in to
vehicle-only filtering for backwards compatibility with traffic code paths.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import numpy as np
import cv2

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logging.warning("ultralytics YOLO not installed. Install with: pip install ultralytics")

logger = logging.getLogger(__name__)


# Full 80-class COCO taxonomy — used by YOLOv8, YOLO11, and YOLO26.
COCO_CLASSES: Dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
    25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite",
    34: "baseball bat", 35: "baseball glove", 36: "skateboard",
    37: "surfboard", 38: "tennis racket", 39: "bottle", 40: "wine glass",
    41: "cup", 42: "fork", 43: "knife", 44: "spoon", 45: "bowl", 46: "banana",
    47: "apple", 48: "sandwich", 49: "orange", 50: "broccoli", 51: "carrot",
    52: "hot dog", 53: "pizza", 54: "donut", 55: "cake", 56: "chair",
    57: "couch", 58: "potted plant", 59: "bed", 60: "dining table",
    61: "toilet", 62: "tv", 63: "laptop", 64: "mouse", 65: "remote",
    66: "keyboard", 67: "cell phone", 68: "microwave", 69: "oven",
    70: "toaster", 71: "sink", 72: "refrigerator", 73: "book", 74: "clock",
    75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier",
    79: "toothbrush",
}

# Semantic super-categories — useful for rule authoring and UI filters.
CLASS_CATEGORY: Dict[str, str] = {
    # People & vehicles
    "person": "person",
    "bicycle": "vehicle", "car": "vehicle", "motorcycle": "vehicle",
    "airplane": "vehicle", "bus": "vehicle", "train": "vehicle",
    "truck": "vehicle", "boat": "vehicle",
    # Animals
    "bird": "animal", "cat": "animal", "dog": "animal", "horse": "animal",
    "sheep": "animal", "cow": "animal", "elephant": "animal", "bear": "animal",
    "zebra": "animal", "giraffe": "animal",
    # Infrastructure
    "traffic light": "infra", "fire hydrant": "infra", "stop sign": "infra",
    "parking meter": "infra", "bench": "infra",
    # Belongings (useful for "unattended bag" rules)
    "backpack": "belongings", "umbrella": "belongings", "handbag": "belongings",
    "tie": "belongings", "suitcase": "belongings",
}


def coco_category(class_name: str) -> str:
    """Return the super-category for a COCO class. Defaults to 'object'."""
    return CLASS_CATEGORY.get(class_name, "object")


class VehicleType(str, Enum):
    """Enumeration of vehicle types detected in traffic."""
    CAR = "car"
    TRUCK = "truck"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    VAN = "van"
    UNKNOWN = "unknown"


@dataclass
class Detection:
    """
    Represents a single object detection in a frame.

    Attributes:
        class_id: YOLO class ID for the detected object
        class_name: Human-readable class name (e.g., 'person', 'car')
        confidence: Detection confidence score (0-1)
        bbox: Bounding box as (x1, y1, x2, y2) in absolute pixel coordinates
        centroid: Center point (x, y) of the bounding box
        area: Area of the bounding box in pixels
        vehicle_type: VehicleType enum if applicable, None for non-vehicles
        frame_index: Index of the frame this detection appeared in
    """
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    centroid: Tuple[float, float]  # (x, y)
    area: float
    vehicle_type: Optional[VehicleType] = None
    frame_index: int = 0

    def get_width(self) -> float:
        """Get bounding box width."""
        return self.bbox[2] - self.bbox[0]

    def get_height(self) -> float:
        """Get bounding box height."""
        return self.bbox[3] - self.bbox[1]

    def get_aspect_ratio(self) -> float:
        """Get width-to-height ratio."""
        height = self.get_height()
        return self.get_width() / height if height > 0 else 0

    def iou(self, other: "Detection") -> float:
        """
        Calculate Intersection over Union (IoU) with another detection.

        Args:
            other: Another Detection object

        Returns:
            IoU score between 0 and 1
        """
        x1_min, y1_min, x1_max, y1_max = self.bbox
        x2_min, y2_min, x2_max, y2_max = other.bbox

        # Calculate intersection
        inter_xmin = max(x1_min, x2_min)
        inter_ymin = max(y1_min, y2_min)
        inter_xmax = min(x1_max, x2_max)
        inter_ymax = min(y1_max, y2_max)

        if inter_xmax < inter_xmin or inter_ymax < inter_ymin:
            return 0.0

        inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
        union_area = self.area + other.area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0


class VehicleDetector:
    """
    Universal YOLO-based scene detector.

    Historically named ``VehicleDetector`` because the first use case was
    traffic. Now emits detections for all 80 COCO classes by default
    (people, vehicles, animals, belongings, infrastructure). A
    ``vehicle_only`` flag preserves the legacy traffic-only pipeline path.

    Works transparently with YOLO26, YOLO11, and YOLOv8 weights because
    Ultralytics keeps the inference API stable across versions.
    """

    # Full 80-class COCO taxonomy — kept as a class attribute so callers
    # (rule engine, UI filters, tracker) can import it cheaply.
    YOLO_CLASS_MAPPING = COCO_CLASSES

    # Classes that should receive a VehicleType tag — used for the
    # back-compat traffic heuristics (incident detector, plate OCR targeting).
    VEHICLE_CLASSES = {
        "car", "truck", "bus", "motorcycle", "bicycle", "van",
    }

    def __init__(
        self,
        model_path: str = "yolo26s.pt",
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        device: Optional[str] = None,
        max_detections: int = 300,
    ):
        """
        Initialize the YOLO detector.

        Args:
            model_path: Path to YOLO model file or model name. Defaults to
                ``yolo26s.pt`` (2026 release, NMS-free, ~43% faster CPU than
                YOLO11). Falls back transparently to YOLO11/YOLOv8 weights
                if the 26 weights are unavailable.
            confidence_threshold: Minimum confidence score (0-1) for detections
            iou_threshold: NMS IOU threshold for removing overlapping detections
            device: Device to run model on ('cpu', 'cuda', or None for auto)
            max_detections: Maximum number of detections per frame

        Raises:
            RuntimeError: If YOLO is not available or model cannot be loaded
        """
        if not YOLO_AVAILABLE:
            raise RuntimeError(
                "YOLO not available. Install ultralytics: pip install ultralytics"
            )

        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections

        # Auto-detect device if not specified
        if device is None:
            device = "cuda" if self._cuda_available() else "cpu"

        self.device = device
        self.model_path = model_path
        logger.info(f"Loading YOLO model: {model_path} on device: {device}")

        # Graceful fallback: YOLO26 → YOLO11 → YOLOv8m if the requested
        # weights aren't cached locally. The Ultralytics API is identical.
        fallback_chain = [model_path]
        lowered = model_path.lower()
        if "yolo26" in lowered or "yolov26" in lowered:
            fallback_chain += ["yolo11s.pt", "yolov8m.pt"]
        elif "yolo11" in lowered:
            fallback_chain += ["yolov8m.pt"]

        last_err: Optional[Exception] = None
        self.model = None
        for candidate in fallback_chain:
            try:
                self.model = YOLO(candidate)
                self.model.to(device)
                if candidate != model_path:
                    logger.warning(
                        f"Requested model '{model_path}' unavailable; "
                        f"loaded fallback '{candidate}'"
                    )
                self.model_path = candidate
                break
            except Exception as e:  # pragma: no cover — network / FS errors
                last_err = e
                logger.warning(f"Failed to load {candidate}: {e}")

        if self.model is None:
            logger.error(f"Failed to load any YOLO model: {last_err}")
            raise RuntimeError(f"Failed to load YOLO model: {last_err}")

        # Cache the class name map actually provided by the loaded model
        # (YOLO26 keeps COCO ordering, but this guards against custom weights).
        model_names = getattr(self.model, "names", None)
        if isinstance(model_names, dict) and model_names:
            self._class_names = {int(k): str(v) for k, v in model_names.items()}
        else:
            self._class_names = dict(COCO_CLASSES)

        logger.info(
            f"YOLO model loaded: {self.model_path} "
            f"({len(self._class_names)} classes)"
        )

    @staticmethod
    def _cuda_available() -> bool:
        """Check if CUDA is available for GPU processing."""
        try:
            import torch
            return torch.cuda.is_available()
        except (ImportError, AttributeError):
            return False

    def detect_frame(
        self,
        frame: np.ndarray,
        frame_index: int = 0,
        vehicle_only: bool = False,
    ) -> List[Detection]:
        """
        Detect objects in a single frame.

        Args:
            frame: Input frame as numpy array (RGB or BGR)
            frame_index: Index of the frame for tracking purposes
            vehicle_only: If True, only return vehicle detections (legacy path)

        Returns:
            List of Detection objects sorted by confidence (descending)
        """
        if frame is None or frame.size == 0:
            logger.warning("Empty frame provided to detect_frame")
            return []

        try:
            # Run inference
            results = self.model(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )

            detections = []

            if results and len(results) > 0:
                result = results[0]

                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes

                    for i in range(min(len(boxes), self.max_detections)):
                        class_id = int(boxes.cls[i])
                        class_name = self._class_names.get(
                            class_id,
                            f"class_{class_id}"
                        )

                        # Legacy traffic path: keep only vehicles.
                        if vehicle_only and class_name not in self.VEHICLE_CLASSES:
                            continue

                        confidence = float(boxes.conf[i])

                        # Get bounding box coordinates
                        xyxy = boxes.xyxy[i]
                        x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])

                        # Calculate centroid
                        cx = (x1 + x2) / 2
                        cy = (y1 + y2) / 2

                        # Calculate area
                        area = (x2 - x1) * (y2 - y1)

                        # Determine vehicle type
                        vehicle_type = self._classify_vehicle_type(class_name)

                        detection = Detection(
                            class_id=class_id,
                            class_name=class_name,
                            confidence=confidence,
                            bbox=(x1, y1, x2, y2),
                            centroid=(cx, cy),
                            area=area,
                            vehicle_type=vehicle_type,
                            frame_index=frame_index,
                        )
                        detections.append(detection)

            # Sort by confidence
            detections.sort(key=lambda d: d.confidence, reverse=True)

            logger.debug(
                f"Frame {frame_index}: detected {len(detections)} objects"
            )
            return detections

        except Exception as e:
            logger.error(f"Error during detection: {e}")
            return []

    def detect_batch(
        self,
        frames: List[np.ndarray],
        start_index: int = 0,
    ) -> List[List[Detection]]:
        """
        Detect objects in multiple frames (batch processing).

        Args:
            frames: List of input frames as numpy arrays
            start_index: Starting frame index for tracking purposes

        Returns:
            List of detection lists, one per frame
        """
        if not frames:
            logger.warning("Empty frames list provided to detect_batch")
            return []

        logger.info(f"Processing batch of {len(frames)} frames")
        batch_detections = []

        try:
            # Process all frames at once for efficiency
            results = self.model(
                frames,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )

            for frame_idx, result in enumerate(results):
                frame_detections = []
                actual_index = start_index + frame_idx

                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes

                    for i in range(min(len(boxes), self.max_detections)):
                        class_id = int(boxes.cls[i])
                        class_name = self._class_names.get(
                            class_id,
                            f"class_{class_id}"
                        )
                        confidence = float(boxes.conf[i])

                        xyxy = boxes.xyxy[i]
                        x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])

                        cx = (x1 + x2) / 2
                        cy = (y1 + y2) / 2
                        area = (x2 - x1) * (y2 - y1)

                        vehicle_type = self._classify_vehicle_type(class_name)

                        detection = Detection(
                            class_id=class_id,
                            class_name=class_name,
                            confidence=confidence,
                            bbox=(x1, y1, x2, y2),
                            centroid=(cx, cy),
                            area=area,
                            vehicle_type=vehicle_type,
                            frame_index=actual_index,
                        )
                        frame_detections.append(detection)

                frame_detections.sort(key=lambda d: d.confidence, reverse=True)
                batch_detections.append(frame_detections)

            logger.info(
                f"Batch processing complete: "
                f"{sum(len(d) for d in batch_detections)} total detections"
            )
            return batch_detections

        except Exception as e:
            logger.error(f"Error during batch detection: {e}")
            return [[] for _ in frames]

    @staticmethod
    def _classify_vehicle_type(class_name: str) -> Optional[VehicleType]:
        """
        Classify a detection into a specific vehicle type.

        Args:
            class_name: YOLO class name from detection

        Returns:
            VehicleType enum or None if not a vehicle
        """
        class_mapping = {
            "car": VehicleType.CAR,
            "truck": VehicleType.TRUCK,
            "bus": VehicleType.BUS,
            "motorcycle": VehicleType.MOTORCYCLE,
            "bicycle": VehicleType.BICYCLE,
            "van": VehicleType.VAN,
            "person": None,
        }
        return class_mapping.get(class_name, None)

    def get_model_info(self) -> dict:
        """
        Get information about the loaded model.

        Returns:
            Dictionary with model metadata
        """
        path_lower = self.model_path.lower() if self.model_path else ""
        if "yolo26" in path_lower or "yolov26" in path_lower:
            family = "YOLO26"
        elif "yolo11" in path_lower:
            family = "YOLO11"
        else:
            family = "YOLOv8"

        return {
            "model_type": family,
            "model_path": self.model_path,
            "device": self.device,
            "confidence_threshold": self.confidence_threshold,
            "iou_threshold": self.iou_threshold,
            "max_detections": self.max_detections,
            "num_classes": len(self._class_names),
            "classes": list(self._class_names.values()),
        }


# Friendlier alias for the universal use case. Import this in new code;
# ``VehicleDetector`` stays for back-compat with the traffic call sites.
SceneDetector = VehicleDetector
