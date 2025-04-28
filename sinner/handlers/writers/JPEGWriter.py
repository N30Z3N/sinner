import cv2

from sinner.handlers.writers.BaseImageWriter import BaseImageWriter


class JPEGWriter(BaseImageWriter):
    """Обработчик для JPEG изображений"""
    extension = ".jpg"
    mime_type = "image/jpeg"

    # Качество JPEG (0-100), где 100 - лучшее качество
    quality: int = 95

    def _get_write_params(self) -> list[int]:
        return [cv2.IMWRITE_JPEG_QUALITY, self.quality]

    def _get_quality(self) -> int:
        return self.quality

    def _set_quality(self, value: int) -> None:
        self.quality = value
