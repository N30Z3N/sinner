import os
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
from psutil import WINDOWS

from sinner.Singleton import SingletonABCMeta
from sinner.typing import Frame


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
