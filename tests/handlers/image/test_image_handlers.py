import os
import shutil

import pytest
from pathlib import Path

from sinner.handlers.writers.BaseImageWriter import BaseImageWriter
from sinner.handlers.writers.JPEGHandler import JPEGWriter
from sinner.handlers.writers.PNGHandler import PNGWriter
from tests.constants import tmp_dir, source_jpg


@pytest.fixture
def cleanup_tmp_dir():
    """Фикстура для подготовки и очистки временной директории"""
    # Подготовка - убедиться, что директория существует
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)

    yield

    # Очистка - удалить тестовые файлы
    for filename in os.listdir(tmp_dir):
        if filename.startswith('test_') and filename.endswith(('.jpg', '.png', '.webp')):
            os.remove(os.path.join(tmp_dir, filename))


@pytest.fixture
def test_image_path():
    """Возвращает путь к тестовому изображению"""
    return source_jpg


@pytest.fixture
def test_output_path():
    """Возвращает базовый путь для тестовых выходных файлов"""
    return os.path.join(tmp_dir, 'test_output')


# Тесты адаптированы под исправленную реализацию BaseImageHandler.read() как статического метода.

class TestBaseImageHandler:
    """Тесты для базового класса обработчика изображений"""

    def test_abstract_methods(self):
        """Проверка, что нельзя создать экземпляр BaseImageHandler"""
        with pytest.raises(TypeError):
            # Попытка создать экземпляр абстрактного класса должна вызвать ошибку
            BaseImageWriter()


class TestJPEGHandler:
    """Тесты для обработчика JPEG изображений"""

    def test_singleton_pattern(self):
        """Проверка, что работает паттерн Singleton"""
        handler1 = JPEGWriter()
        handler2 = JPEGWriter()
        assert handler1 is handler2  # Должны быть одним и тем же объектом

    def test_read_jpeg(self, test_image_path):
        """Проверка чтения JPEG-изображения"""
        # Использование статического метода read
        image = JPEGWriter.read(test_image_path)

        assert image is not None
        assert len(image.shape) == 3  # Должно быть 3D (высота, ширина, каналы)
        assert image.shape[2] == 3  # Три цветовых канала (RGB)

    def test_write_jpeg(self, test_image_path, test_output_path, cleanup_tmp_dir):
        """Проверка записи JPEG-изображения"""
        handler = JPEGWriter()
        # Используем статический метод read
        image = JPEGWriter.read(test_image_path)

        # Проверка базовой записи
        output_path = f"{test_output_path}_jpeg"
        result = handler.write(image, output_path)
        assert result is True
        assert os.path.exists(f"{output_path}.jpg")

        # Проверка чтения записанного файла
        written_image = handler.read(f"{output_path}.jpg")
        assert written_image is not None
        assert written_image.shape == image.shape

    def test_jpeg_quality(self, test_image_path, test_output_path, cleanup_tmp_dir):
        """Проверка влияния параметра качества JPEG"""
        handler = JPEGWriter()
        # Используем статический метод read
        image = JPEGWriter.read(test_image_path)

        # Запись с высоким качеством
        handler.quality = 95
        high_quality_path = f"{test_output_path}_high_quality.jpg"
        handler.write(image, high_quality_path)

        # Запись с низким качеством
        handler.quality = 10
        low_quality_path = f"{test_output_path}_low_quality.jpg"
        handler.write(image, low_quality_path)

        # Размер файла с низким качеством должен быть меньше
        high_size = os.path.getsize(high_quality_path)
        low_size = os.path.getsize(low_quality_path)
        assert low_size < high_size


class TestPNGHandler:
    """Тесты для обработчика PNG изображений"""

    def test_read_png(self, test_output_path, cleanup_tmp_dir):
        """Проверка чтения PNG-изображения"""
        # Сначала создаем PNG файл
        handler = PNGWriter()
        # Используем статический метод read
        image = JPEGWriter.read(source_jpg)

        png_path = f"{test_output_path}_png.png"
        handler.write(image, png_path)

        # Теперь читаем созданный PNG файл
        png_image = PNGWriter.read(png_path)

        assert png_image is not None
        assert len(png_image.shape) == 3
        assert png_image.shape[2] == 3

    def test_png_compression(self, test_image_path, test_output_path, cleanup_tmp_dir):
        """Проверка влияния уровня сжатия PNG"""
        handler = PNGWriter()
        # Используем статический метод read
        image = JPEGWriter.read(test_image_path)

        # Запись с низким сжатием
        handler.compression_level = 1
        low_comp_path = f"{test_output_path}_low_comp.png"
        handler.write(image, low_comp_path)

        # Запись с высоким сжатием
        handler.compression_level = 9
        high_comp_path = f"{test_output_path}_high_comp.png"
        handler.write(image, high_comp_path)

        # Размеры должны различаться, но изображения должны быть идентичными
        low_size = os.path.getsize(low_comp_path)
        high_size = os.path.getsize(high_comp_path)

        # Обычно файл с высоким сжатием меньше, но это не всегда так с PNG
        # Главное - проверить, что файлы различаются
        assert low_size != high_size


class TestFormatConversion:
    """Тесты для конвертации между форматами"""

    def test_jpeg_to_png(self, test_image_path, test_output_path, cleanup_tmp_dir):
        """Проверка конвертации из JPEG в PNG"""
        png_handler = PNGWriter()

        # Используем статический метод read
        image = JPEGWriter.read(test_image_path)

        # Сохраняем как PNG
        png_path = f"{test_output_path}_jpeg_to_png.png"
        png_handler.write(image, png_path)

        # Читаем обратно
        png_image = PNGWriter.read(png_path)

        # Проверяем, что размеры совпадают
        assert png_image.shape == image.shape


class TestEdgeCases:
    """Тесты для граничных случаев"""

    def test_file_extension_handling(self, test_image_path, test_output_path, cleanup_tmp_dir):
        """Проверка обработки расширения файла"""
        jpeg_handler = JPEGWriter()

        image = JPEGWriter.read(test_image_path)

        # Путь без расширения
        path_without_ext = test_output_path
        jpeg_handler.write(image, path_without_ext)

        # Должен быть создан файл с расширением .jpg
        assert os.path.exists(f"{path_without_ext}.jpg")

    def test_directory_creation(self, test_image_path, cleanup_tmp_dir):
        """Проверка создания директории при записи"""
        jpeg_handler = JPEGWriter()

        image = JPEGWriter.read(test_image_path)

        # Путь с несуществующей директорией
        new_dir = os.path.join(tmp_dir, 'new_directory')
        if os.path.exists(new_dir):
            shutil.rmtree(new_dir)

        output_path = os.path.join(new_dir, 'test_file.jpg')
        jpeg_handler.write(image, output_path)

        # Проверяем, что директория и файл созданы
        assert os.path.exists(new_dir)
        assert os.path.exists(output_path)
