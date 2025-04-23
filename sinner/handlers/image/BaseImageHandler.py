import os
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
from numpy import fromfile, uint8, dstack
from psutil import WINDOWS

from sinner.Singleton import SingletonABCMeta
from sinner.typing import Frame


class BaseImageHandler(ABC, metaclass=SingletonABCMeta):
    """Базовый абстрактный класс для обработки изображений"""

    # Расширение файла по умолчанию
    extension: str = ""
    # Mime-тип файла
    mime_type: str = ""

    @staticmethod
    def read(path: str) -> Frame:
        """Чтение изображения из файла"""
        if WINDOWS:
            image = cv2.imdecode(fromfile(path, dtype=uint8), cv2.IMREAD_UNCHANGED)
            if len(image.shape) == 2:  # Исправляет проблему с черно-белыми изображениями
                image = dstack([image] * 3)
            if image.shape[2] == 4:  # Исправляет проблему с альфа-каналом
                image = image[:, :, :3]
            return image
        else:
            return cv2.imread(path)

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
