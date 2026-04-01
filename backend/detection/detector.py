"""
YOLOv8-based vehicle, person, and incident detection module.

Provides high-performance object detection for traffic surveillance including
vehicle classification, person detection, and batch processing capabilities.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
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
    YOLOv8-based detector for vehicles, persons, and other traffic objects.

    Supports configurable confidence thresholds, device selection, and batch processing.
    """

    # YOLO class IDs
    YOLO_CLASS_MAPPING = {
        0: "person",
        2: "car",
        3: "motorcycle",
        5: "bus",
        7: "truck",
        1: "bicycle",
    }

    def __init__(
        self,
        model_path: str = "yolov8m.pt",
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        device: Optional[str] = None,
        max_detections: int = 300,
    ):
        """
        Initialize the YOLOv8 detector.

        Args:
            model_path: Path to YOLO model file or model name (e.g., 'yolov8m.pt')
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
        logger.info(f"Loading YOLO model: {model_path} on device: {device}")

        try:
            self.model = YOLO(model_path)
            self.model.to(device)
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise RuntimeError(f"Failed to load YOLO model: {e}")

        logger.info("YOLO model loaded successfully")

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
            vehicle_only: If True, only return vehicle detections

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
                        class_name = self.YOLO_CLASS_MAPPING.get(
                            class_id,
                            f"class_{class_id}"
                        )

                        # Skip non-relevant classes if vehicle_only is True
                        if vehicle_only and class_name == "person":
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
                        class_name = self.YOLO_CLASS_MAPPING.get(
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
        return {
            "model_type": "YOLOv8",
            "device": self.device,
            "confidence_threshold": self.confidence_threshold,
            "iou_threshold": self.iou_threshold,
            "max_detections": self.max_detections,
            "classes": list(self.YOLO_CLASS_MAPPING.values()),
        }
