"""
Traffic Density Heatmap Generator.

Generates traffic density heatmaps from vehicle detection data using
grid-based accumulation with Gaussian blur for smooth visualization.
Converts to RGBA images for WebSocket transmission and dashboard display.

Features:
    - Grid-based accumulation of detection positions
    - Gaussian blur for smooth density representation
    - Temporal decay for recent activity emphasis
    - Color mapping (blue → green → yellow → red)
    - Base64 PNG encoding for WebSocket transmission
    - Real-time heatmap updates
    - Configurable cell size and normalization
"""

import logging
from typing import Optional, Tuple
import base64
from io import BytesIO

import numpy as np
import cv2

logger = logging.getLogger(__name__)


class TrafficHeatmap:
    """
    Generates and manages traffic density heatmaps.

    Accumulates vehicle detection positions on a grid and applies
    Gaussian blur for smooth visualization. Supports temporal decay
    to emphasize recent activity and provides color-mapped visualization.
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        cell_size: int = 20,
    ):
        """
        Initialize heatmap generator.

        Args:
            width: Width of frame in pixels
            height: Height of frame in pixels
            cell_size: Size of grid cells in pixels (larger = coarser, faster)
        """
        self.width = width
        self.height = height
        self.cell_size = cell_size

        # Calculate grid dimensions
        self.grid_height = (height + cell_size - 1) // cell_size
        self.grid_width = (width + cell_size - 1) // cell_size

        # Initialize accumulation grid
        self.grid = np.zeros((self.grid_height, self.grid_width), dtype=np.float32)

        logger.info(
            f"TrafficHeatmap initialized: {width}x{height} -> "
            f"{self.grid_width}x{self.grid_height} grid (cell_size={cell_size})"
        )

    def add_detection(self, x: float, y: float, weight: float = 1.0) -> None:
        """
        Add a single detection point to the heatmap.

        Args:
            x: X coordinate of detection centroid
            y: Y coordinate of detection centroid
            weight: Weight to apply (confidence score recommended)
        """
        # Convert pixel coordinates to grid coordinates
        grid_x = int(x / self.cell_size)
        grid_y = int(y / self.cell_size)

        # Bounds checking
        if 0 <= grid_x < self.grid_width and 0 <= grid_y < self.grid_height:
            self.grid[grid_y, grid_x] += weight

    def add_detections_batch(self, detections: list) -> None:
        """
        Add a batch of detections to the heatmap.

        Args:
            detections: List of detection dictionaries with 'centroid' and 'confidence'
        """
        for detection in detections:
            if "centroid" in detection:
                x, y = detection["centroid"]
                confidence = detection.get("confidence", 1.0)
                self.add_detection(x, y, weight=confidence)

    def get_heatmap(self, normalize: bool = True) -> np.ndarray:
        """
        Get the raw heatmap as a 2D numpy array.

        Args:
            normalize: If True, normalize to 0-255 range

        Returns:
            2D numpy array with heatmap values
        """
        if normalize:
            max_val = np.max(self.grid)
            if max_val > 0:
                heatmap = (self.grid / max_val * 255).astype(np.uint8)
            else:
                heatmap = self.grid.astype(np.uint8)
        else:
            heatmap = self.grid.astype(np.uint8)

        return heatmap

    def get_heatmap_overlay(
        self,
        alpha: float = 0.4,
        apply_blur: bool = True,
        blur_kernel: int = 21,
    ) -> np.ndarray:
        """
        Get colored RGBA heatmap overlay image.

        Applies Gaussian blur for smoothness and creates color-mapped
        visualization: blue (low) → green → yellow → red (high).

        Args:
            alpha: Transparency of overlay (0-1)
            apply_blur: Whether to apply Gaussian blur
            blur_kernel: Kernel size for Gaussian blur (must be odd)

        Returns:
            RGBA image array (height, width, 4) ready for overlay
        """
        # Get normalized heatmap
        heatmap = self.get_heatmap(normalize=True)

        # Apply Gaussian blur for smoothness
        if apply_blur:
            # Ensure kernel size is odd
            if blur_kernel % 2 == 0:
                blur_kernel += 1
            heatmap = cv2.GaussianBlur(heatmap, (blur_kernel, blur_kernel), 0)

        # Apply color mapping: blue → green → yellow → red
        # Use OpenCV's COLORMAP_JET for standard jet colormap
        heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

        # Convert BGR to RGB
        heatmap_rgb = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

        # Create RGBA image with alpha transparency
        rgba_image = np.zeros((heatmap_rgb.shape[0], heatmap_rgb.shape[1], 4), dtype=np.uint8)
        rgba_image[:, :, :3] = heatmap_rgb
        rgba_image[:, :, 3] = (heatmap * alpha).astype(np.uint8)

        return rgba_image

    def to_base64_png(
        self,
        apply_blur: bool = True,
        blur_kernel: int = 21,
        alpha: float = 0.4,
    ) -> str:
        """
        Export heatmap as base64-encoded PNG.

        Creates a color-mapped heatmap image and encodes it as
        base64 PNG for efficient WebSocket transmission.

        Args:
            apply_blur: Whether to apply Gaussian blur
            blur_kernel: Kernel size for Gaussian blur
            alpha: Transparency of overlay

        Returns:
            Base64-encoded PNG string (can be used as img src)
        """
        # Get colored heatmap
        overlay = self.get_heatmap_overlay(
            alpha=alpha,
            apply_blur=apply_blur,
            blur_kernel=blur_kernel,
        )

        # Ensure it's in BGR format for cv2.imwrite
        bgr_image = cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGR)

        # Encode as PNG
        success, png_buffer = cv2.imencode(".png", bgr_image)

        if not success:
            logger.error("Failed to encode heatmap to PNG")
            return ""

        # Convert to base64
        png_bytes = png_buffer.tobytes()
        base64_string = base64.b64encode(png_bytes).decode("utf-8")

        return f"data:image/png;base64,{base64_string}"

    def decay(self, factor: float = 0.95) -> None:
        """
        Apply temporal decay to heatmap values.

        Multiplies all grid values by decay factor, emphasizing
        recent activity over historical data. Useful for continuous
        processing to prevent "ghosting" of old detections.

        Args:
            factor: Decay multiplier (0-1), typically 0.95-0.99
        """
        if not (0 < factor <= 1):
            logger.warning(f"Decay factor should be 0-1, got {factor}")
            factor = max(0.01, min(1, factor))

        self.grid *= factor
        logger.debug(f"Applied decay factor {factor} to heatmap")

    def reset(self) -> None:
        """Clear all heatmap data."""
        self.grid.fill(0)
        logger.debug("Heatmap reset")

    def get_statistics(self) -> dict:
        """
        Get heatmap statistics.

        Returns:
            Dictionary with min, max, mean, std values
        """
        return {
            "min": float(np.min(self.grid)),
            "max": float(np.max(self.grid)),
            "mean": float(np.mean(self.grid)),
            "std": float(np.std(self.grid)),
            "total_accumulation": float(np.sum(self.grid)),
        }

    def get_high_density_regions(self, threshold_percentile: int = 75) -> list:
        """
        Identify high-density regions in the heatmap.

        Useful for identifying traffic hotspots and congestion areas.

        Args:
            threshold_percentile: Percentile threshold (0-100)

        Returns:
            List of (x, y) pixel coordinates of high-density cells
        """
        threshold_value = np.percentile(self.grid, threshold_percentile)
        high_density_cells = np.argwhere(self.grid >= threshold_value)

        # Convert grid coordinates back to pixel coordinates
        high_density_pixels = [
            (int(cell[1] * self.cell_size + self.cell_size / 2),
             int(cell[0] * self.cell_size + self.cell_size / 2))
            for cell in high_density_cells
        ]

        return high_density_pixels

    def resize(self, new_width: int, new_height: int) -> None:
        """
        Resize heatmap grid to match new frame dimensions.

        Args:
            new_width: New frame width
            new_height: New frame height
        """
        old_grid = self.grid.copy()

        self.width = new_width
        self.height = new_height
        self.grid_height = (new_height + self.cell_size - 1) // self.cell_size
        self.grid_width = (new_width + self.cell_size - 1) // self.cell_size
        self.grid = np.zeros((self.grid_height, self.grid_width), dtype=np.float32)

        # Attempt to preserve data proportionally
        scale_x = self.grid_width / old_grid.shape[1] if old_grid.shape[1] > 0 else 1
        scale_y = self.grid_height / old_grid.shape[0] if old_grid.shape[0] > 0 else 1

        for y in range(old_grid.shape[0]):
            for x in range(old_grid.shape[1]):
                new_y = int(y * scale_y)
                new_x = int(x * scale_x)
                if 0 <= new_y < self.grid_height and 0 <= new_x < self.grid_width:
                    self.grid[new_y, new_x] = old_grid[y, x]

        logger.info(f"Heatmap resized to {new_width}x{new_height}")

    def save_to_file(self, filepath: str, apply_blur: bool = True) -> bool:
        """
        Save heatmap visualization to file.

        Args:
            filepath: Path to save PNG file
            apply_blur: Whether to apply Gaussian blur

        Returns:
            True if successful, False otherwise
        """
        try:
            overlay = self.get_heatmap_overlay(apply_blur=apply_blur)
            bgr_image = cv2.cvtColor(overlay, cv2.COLOR_RGBA2BGR)
            success = cv2.imwrite(filepath, bgr_image)
            if success:
                logger.info(f"Heatmap saved to {filepath}")
            return success
        except Exception as e:
            logger.error(f"Failed to save heatmap: {e}")
            return False
