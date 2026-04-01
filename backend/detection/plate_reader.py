"""
License plate detection and Optical Character Recognition (OCR) module.

Detects license plates in vehicle regions and extracts text using EasyOCR.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import cv2

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logging.warning("easyocr not installed. Install with: pip install easyocr")

logger = logging.getLogger(__name__)


@dataclass
class PlateDetection:
    """
    Represents a detected and recognized license plate.

    Attributes:
        text: Extracted text from the plate
        confidence: OCR confidence score (0-1)
        bbox: Bounding box of the plate (x1, y1, x2, y2)
        vehicle_bbox: Bounding box of the parent vehicle
        raw_text: Raw text before validation/cleanup
        is_valid: Whether the plate passed validation rules
        country_code: Optional country code if identifiable
    """
    text: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    vehicle_bbox: Tuple[float, float, float, float]
    raw_text: str = ""
    is_valid: bool = False
    country_code: Optional[str] = None

    def get_width(self) -> float:
        """Get plate width in pixels."""
        return self.bbox[2] - self.bbox[0]

    def get_height(self) -> float:
        """Get plate height in pixels."""
        return self.bbox[3] - self.bbox[1]

    def get_aspect_ratio(self) -> float:
        """Get width-to-height ratio."""
        height = self.get_height()
        return self.get_width() / height if height > 0 else 0


class PlateReader:
    """
    Detects license plates in vehicle regions and extracts text using OCR.

    Uses a secondary YOLO model for plate detection and EasyOCR for text extraction.
    """

    def __init__(
        self,
        plate_model_path: str = "best.pt",
        ocr_languages: List[str] = None,
        ocr_confidence_threshold: float = 0.3,
        min_plate_aspect_ratio: float = 2.0,
        max_plate_aspect_ratio: float = 5.0,
        min_plate_area: float = 500,
    ):
        """
        Initialize the PlateReader.

        Args:
            plate_model_path: Path to YOLO plate detection model
            ocr_languages: Languages for OCR (default: ['en'])
            ocr_confidence_threshold: Minimum OCR confidence score
            min_plate_aspect_ratio: Minimum width/height ratio for plates
            max_plate_aspect_ratio: Maximum width/height ratio for plates
            min_plate_area: Minimum plate area in pixels

        Raises:
            RuntimeError: If required dependencies are not available
        """
        if not EASYOCR_AVAILABLE:
            raise RuntimeError(
                "easyocr not available. Install with: pip install easyocr"
            )

        if ocr_languages is None:
            ocr_languages = ["en"]

        self.ocr_languages = ocr_languages
        self.ocr_confidence_threshold = ocr_confidence_threshold
        self.min_plate_aspect_ratio = min_plate_aspect_ratio
        self.max_plate_aspect_ratio = max_plate_aspect_ratio
        self.min_plate_area = min_plate_area

        # Load plate detection model if available
        self.plate_model = None
        if YOLO_AVAILABLE:
            try:
                logger.info(f"Loading plate detection model: {plate_model_path}")
                self.plate_model = YOLO(plate_model_path)
                logger.info("Plate detection model loaded successfully")
            except Exception as e:
                logger.warning(f"Could not load plate model: {e}. Using fallback method.")

        # Initialize OCR reader
        logger.info(f"Initializing OCR reader for languages: {ocr_languages}")
        self.ocr_reader = easyocr.Reader(
            ocr_languages,
            gpu=self._gpu_available(),
            verbose=False,
        )
        logger.info("OCR reader initialized")

    @staticmethod
    def _gpu_available() -> bool:
        """Check if GPU is available for OCR."""
        try:
            import torch
            return torch.cuda.is_available()
        except (ImportError, AttributeError):
            return False

    def detect_plates(
        self,
        frame: np.ndarray,
        vehicle_boxes: List[Tuple[float, float, float, float]],
    ) -> List[PlateDetection]:
        """
        Detect and recognize license plates in vehicle regions.

        Args:
            frame: Input frame as numpy array (RGB or BGR)
            vehicle_boxes: List of vehicle bounding boxes to search within

        Returns:
            List of PlateDetection objects
        """
        if frame is None or frame.size == 0:
            logger.warning("Empty frame provided to detect_plates")
            return []

        if not vehicle_boxes:
            logger.debug("No vehicle boxes provided")
            return []

        plates = []

        for vehicle_bbox in vehicle_boxes:
            x1, y1, x2, y2 = vehicle_bbox
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # Extract vehicle region
            vehicle_roi = frame[y1:y2, x1:x2]

            if vehicle_roi.size == 0:
                continue

            # Detect plates in this vehicle region
            detected_plates = self._detect_plates_in_roi(
                vehicle_roi,
                vehicle_bbox,
            )

            plates.extend(detected_plates)

        logger.debug(f"Detected {len(plates)} plates in frame")
        return plates

    def _detect_plates_in_roi(
        self,
        roi: np.ndarray,
        vehicle_bbox: Tuple[float, float, float, float],
    ) -> List[PlateDetection]:
        """
        Detect plates within a vehicle region of interest.

        Args:
            roi: Vehicle region of interest
            vehicle_bbox: Original vehicle bounding box coordinates

        Returns:
            List of PlateDetection objects
        """
        plates = []

        # Try YOLO-based detection if model is available
        if self.plate_model is not None:
            plates.extend(
                self._detect_plates_yolo(roi, vehicle_bbox)
            )

        # Fallback: search entire vehicle region
        if not plates:
            plates.extend(
                self._detect_plates_heuristic(roi, vehicle_bbox)
            )

        return plates

    def _detect_plates_yolo(
        self,
        roi: np.ndarray,
        vehicle_bbox: Tuple[float, float, float, float],
    ) -> List[PlateDetection]:
        """
        Detect plates using YOLO model.

        Args:
            roi: Vehicle region of interest
            vehicle_bbox: Original vehicle bounding box coordinates

        Returns:
            List of PlateDetection objects
        """
        plates = []

        try:
            results = self.plate_model(roi, conf=0.3, verbose=False)

            if results and len(results) > 0:
                result = results[0]

                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes
                    roi_height, roi_width = roi.shape[:2]
                    vx1, vy1, vx2, vy2 = vehicle_bbox

                    for i in range(len(boxes)):
                        confidence = float(boxes.conf[i])
                        xyxy = boxes.xyxy[i]
                        px1, py1, px2, py2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])

                        # Convert to absolute coordinates
                        abs_x1 = vx1 + px1
                        abs_y1 = vy1 + py1
                        abs_x2 = vx1 + px2
                        abs_y2 = vy1 + py2

                        plate_bbox = (abs_x1, abs_y1, abs_x2, abs_y2)

                        # Validate plate dimensions
                        if not self._validate_plate_bbox(plate_bbox):
                            continue

                        # Extract and recognize text
                        plate_roi = roi[int(py1):int(py2), int(px1):int(px2)]

                        if plate_roi.size > 0:
                            plate_detection = self._recognize_plate_text(
                                plate_roi,
                                plate_bbox,
                                vehicle_bbox,
                            )

                            if plate_detection is not None:
                                plates.append(plate_detection)

        except Exception as e:
            logger.warning(f"Error in YOLO plate detection: {e}")

        return plates

    def _detect_plates_heuristic(
        self,
        roi: np.ndarray,
        vehicle_bbox: Tuple[float, float, float, float],
    ) -> List[PlateDetection]:
        """
        Detect plates using heuristic methods (fallback).

        Args:
            roi: Vehicle region of interest
            vehicle_bbox: Original vehicle bounding box coordinates

        Returns:
            List of PlateDetection objects
        """
        plates = []

        try:
            # Convert to grayscale
            if len(roi.shape) == 3:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi

            # Apply edge detection
            edges = cv2.Canny(gray, 100, 200)

            # Morphological operations
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

            # Find contours
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            roi_height, roi_width = roi.shape[:2]
            vx1, vy1, vx2, vy2 = vehicle_bbox

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)

                # Check aspect ratio (plates are wider than tall)
                if h > 0 and 2.0 <= w / h <= 5.0:
                    # Check minimum area
                    if w * h >= self.min_plate_area:
                        # Convert to absolute coordinates
                        abs_x1 = vx1 + x
                        abs_y1 = vy1 + y
                        abs_x2 = vx1 + x + w
                        abs_y2 = vy1 + y + h

                        plate_bbox = (abs_x1, abs_y1, abs_x2, abs_y2)

                        # Extract and recognize
                        plate_roi = roi[y:y+h, x:x+w]

                        if plate_roi.size > 0:
                            plate_detection = self._recognize_plate_text(
                                plate_roi,
                                plate_bbox,
                                vehicle_bbox,
                                confidence=0.5,
                            )

                            if plate_detection is not None:
                                plates.append(plate_detection)

        except Exception as e:
            logger.warning(f"Error in heuristic plate detection: {e}")

        return plates

    def _recognize_plate_text(
        self,
        plate_roi: np.ndarray,
        plate_bbox: Tuple[float, float, float, float],
        vehicle_bbox: Tuple[float, float, float, float],
        confidence: Optional[float] = None,
    ) -> Optional[PlateDetection]:
        """
        Recognize text from a detected plate region.

        Args:
            plate_roi: Plate region of interest
            plate_bbox: Plate bounding box in absolute coordinates
            vehicle_bbox: Parent vehicle bounding box
            confidence: Optional detection confidence

        Returns:
            PlateDetection object or None if recognition failed
        """
        try:
            # Preprocess plate image
            plate_roi = self._preprocess_plate_image(plate_roi)

            # Run OCR
            results = self.ocr_reader.readtext(plate_roi, detail=1)

            if not results:
                return None

            # Extract text and confidence
            texts = []
            confidences = []

            for (bbox, text, conf) in results:
                if conf >= self.ocr_confidence_threshold:
                    texts.append(text)
                    confidences.append(conf)

            if not texts:
                return None

            raw_text = "".join(texts)
            ocr_confidence = np.mean(confidences) if confidences else 0.0

            # Clean and validate text
            cleaned_text = self._clean_plate_text(raw_text)
            is_valid = self._validate_plate_text(cleaned_text)

            plate_detection = PlateDetection(
                text=cleaned_text,
                confidence=float(ocr_confidence),
                bbox=plate_bbox,
                vehicle_bbox=vehicle_bbox,
                raw_text=raw_text,
                is_valid=is_valid,
                country_code=self._detect_country_code(cleaned_text),
            )

            logger.debug(
                f"Recognized plate: {cleaned_text} (confidence: {ocr_confidence:.2f}, valid: {is_valid})"
            )

            return plate_detection

        except Exception as e:
            logger.warning(f"Error during plate recognition: {e}")
            return None

    @staticmethod
    def _preprocess_plate_image(image: np.ndarray) -> np.ndarray:
        """
        Preprocess plate image for OCR.

        Args:
            image: Input plate image

        Returns:
            Preprocessed image
        """
        # Resize if too small
        height, width = image.shape[:2]
        if width < 100 or height < 30:
            scale = max(100 / width, 30 / height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

        # Convert to grayscale
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Enhance contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        image = clahe.apply(image)

        # Threshold
        _, image = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)

        return image

    @staticmethod
    def _clean_plate_text(text: str) -> str:
        """
        Clean OCR output by removing unwanted characters.

        Args:
            text: Raw OCR text

        Returns:
            Cleaned text
        """
        # Remove spaces and special characters, keep alphanumeric only
        text = re.sub(r'[^A-Z0-9]', '', text.upper())
        return text.strip()

    @staticmethod
    def _validate_plate_text(text: str) -> bool:
        """
        Validate plate text using heuristics.

        Args:
            text: Cleaned plate text

        Returns:
            True if text appears to be valid plate format
        """
        # Must be at least 4 characters (minimum plate length)
        if len(text) < 4:
            return False

        # Must not be all numbers or all letters
        has_digit = any(c.isdigit() for c in text)
        has_letter = any(c.isalpha() for c in text)

        if not (has_digit and has_letter):
            return False

        # Must be reasonable length (typical plates are 6-12 chars)
        if len(text) > 15:
            return False

        return True

    @staticmethod
    def _validate_plate_bbox(bbox: Tuple[float, float, float, float]) -> bool:
        """
        Validate plate bounding box dimensions.

        Args:
            bbox: Bounding box (x1, y1, x2, y2)

        Returns:
            True if dimensions are reasonable for a plate
        """
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1

        # Aspect ratio check
        if height <= 0:
            return False

        aspect_ratio = width / height

        return 2.0 <= aspect_ratio <= 5.0 and width * height >= 500

    @staticmethod
    def _detect_country_code(text: str) -> Optional[str]:
        """
        Attempt to detect country code from plate text.

        Args:
            text: Cleaned plate text

        Returns:
            Country code string or None
        """
        # Simple heuristic: check for common patterns
        # This is a placeholder - real implementation would use ML or regex patterns

        if len(text) >= 3:
            # Check for US state abbreviations (2 letters)
            if text[:2].isalpha() and len(text) >= 5:
                return "US"

        # Check for European format
        if text.startswith("EU") or (len(text) >= 4 and text[0].isalpha() and text[1:3].isdigit()):
            return "EU"

        return None

    def get_config(self) -> dict:
        """Get configuration information."""
        return {
            "ocr_languages": self.ocr_languages,
            "ocr_confidence_threshold": self.ocr_confidence_threshold,
            "min_plate_aspect_ratio": self.min_plate_aspect_ratio,
            "max_plate_aspect_ratio": self.max_plate_aspect_ratio,
            "min_plate_area": self.min_plate_area,
            "plate_model_available": self.plate_model is not None,
            "gpu_enabled": self._gpu_available(),
        }
