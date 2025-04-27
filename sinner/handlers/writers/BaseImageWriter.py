import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar

import cv2
from psutil import WINDOWS

from sinner.Singleton import SingletonABCMeta
from sinner.typing import Frame

T = TypeVar('T', bound='BaseImageWriter')


class BaseImageWriter(ABC, metaclass=SingletonABCMeta):
    """Базовый абстрактный класс для обработки изображений"""

    # Расширение файла по умолчанию
    extension: str = ""
    # Mime-тип файла
    mime_type: str = ""

    def write(self, image: Frame, path: str) -> bool:
        """Запись изображения в файл"""
        # Создание директорий, если они не существуют
        Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)

        # Проверка, что расширение файла соответствует формату
        if not path.lower().endswith(self.extension):
            path = f"{path}{self.extension}"

        if WINDOWS:
            is_success, im_buf_arr = cv2.imencode(self.extension, image, self._get_write_params())
            im_buf_arr.tofile(path)
            return is_success
        else:
            return cv2.imwrite(path, image, self._get_write_params())

    @abstractmethod
    def _get_write_params(self) -> list[int]:
        pass

    @classmethod
    def create(cls, _format: str = 'png', quality: int = None) -> T:
        """
        Фабричный метод для создания соответствующего writer по формату изображения

        Args:
            _format: Формат изображения ('png' или 'jpg')
            quality: Качество сжатия или параметр компрессии (опционально)

        Returns:
            BaseImageWriter: Соответствующий writer

        Raises:
            ValueError: Если указан неподдерживаемый формат
        """
        from sinner.handlers.writers.JPEGWriter import JPEGWriter
        from sinner.handlers.writers.PNGWriter import PNGWriter

        if _format.lower() == 'png':
            writer = PNGWriter()
            if quality is not None:
                writer.compression_level = quality
            return writer
        elif _format.lower() in ['jpg', 'jpeg']:
            writer = JPEGWriter()
            if quality is not None:
                writer.quality = quality
            return writer
        else:
            raise ValueError(f"Неподдерживаемый формат изображения: {format}")
