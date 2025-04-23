import cv2

from sinner.handlers.image.BaseImageHandler import BaseImageHandler


class PNGHandler(BaseImageHandler):
    """Обработчик для PNG изображений"""
    extension = ".png"
    mime_type = "image/png"

    # Параметр сжатия (0-9), где 9 - максимальное сжатие
    compression_level: int = 3

    def _get_write_params(self) -> list[int]:
        return [cv2.IMWRITE_PNG_COMPRESSION, self.compression_level]
