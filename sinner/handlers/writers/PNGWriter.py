import cv2

from sinner.handlers.writers.BaseImageWriter import BaseImageWriter


class PNGWriter(BaseImageWriter):
    """Обработчик для PNG изображений"""
    extension = ".png"
    mime_type = "image/png"

    # Параметр сжатия (0-9), где 9 - максимальное сжатие
    compression_level: int = 3

    def _get_write_params(self) -> list[int]:
        return [cv2.IMWRITE_PNG_COMPRESSION, self.compression_level]

    def _get_quality(self) -> int:
        # Инвертируем compression_level, т.к. качество и сжатие - обратные понятия
        # 0 сжатия = 100 качество, 9 сжатия = 0 качество
        return round(100 - (self.compression_level / 9 * 100))

    def _set_quality(self, value: int) -> None:
        # Преобразование из качества (0-100) в сжатие (0-9)
        self.compression_level = round((100 - value) / 100 * 9)