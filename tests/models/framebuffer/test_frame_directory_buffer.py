import os
import threading
import pytest
import shutil
import numpy as np
from unittest.mock import patch

from sinner.models.NumberedFrame import NumberedFrame
from sinner.helpers.FrameHelper import read_from_image
from sinner.models.framebuffer.FrameDirectoryBuffer import FrameDirectoryBuffer
from sinner.handlers.writers.PNGWriter import PNGWriter
# Импортируем тестовые константы
from tests.constants import (
    tmp_dir, target_mp4, source_jpg,
    TARGET_FC, FRAME_SHAPE
)


@pytest.fixture
def cleanup_temp_dir():
    """Фикстура для очистки временной директории после тестов."""
    test_temp_dir = os.path.join(tmp_dir, 'test_frame_buffer')

    # Создаем директорию, если она не существует
    if not os.path.exists(test_temp_dir):
        os.makedirs(test_temp_dir)

    yield test_temp_dir

    # Очищаем после тестов
    if os.path.exists(test_temp_dir):
        shutil.rmtree(test_temp_dir)


@pytest.fixture
def frame_buffer(cleanup_temp_dir):
    """Создает экземпляр FrameDirectoryBuffer с реальной временной директорией."""
    return FrameDirectoryBuffer(cleanup_temp_dir, PNGWriter())


@pytest.fixture
def loaded_frame_buffer(frame_buffer):
    """Создает предварительно загруженный кадровый буфер с реальными файлами."""
    frame_buffer.load(source_jpg, target_mp4, TARGET_FC)
    return frame_buffer


@pytest.fixture
def sample_frame():
    """Создает тестовый кадр для использования в тестах."""
    # Используем read_from_image для загрузки реального изображения из ассетов
    try:
        # Пытаемся прочитать реальное изображение из ассетов
        image = read_from_image(source_jpg)
    except Exception:
        # В случае ошибки создаем пустой кадр
        image = np.zeros(FRAME_SHAPE, dtype=np.uint8)

    return NumberedFrame(1, image)


class TestFrameDirectoryBufferInit:
    """Тесты для инициализации и базовых свойств FrameDirectoryBuffer."""

    def test_init(self, cleanup_temp_dir):
        """Проверка корректной инициализации объекта."""
        buffer = FrameDirectoryBuffer(cleanup_temp_dir, PNGWriter())
        assert buffer.endpoint_name == 'preview'
        assert buffer._loaded is False
        assert buffer._indices == []
        assert buffer.temp_dir.endswith('preview')

    def test_temp_dir_validation(self):
        """Проверка валидации относительных путей в temp_dir."""
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.is_absolute_path', return_value=False), \
                pytest.raises(Exception, match="Relative paths are not supported"):
            FrameDirectoryBuffer("relative/path")


class TestFrameDirectoryBufferLoad:
    """Тесты для методов загрузки и очистки."""

    def test_load(self, frame_buffer):
        """Проверка загрузки источника и цели в буфер."""
        buffer = frame_buffer.load(source_jpg, target_mp4, TARGET_FC)

        assert buffer._source_name == source_jpg
        assert buffer._target_name == target_mp4
        assert buffer._frames_count == TARGET_FC
        assert buffer._loaded is True
        assert buffer.zfill_length == len(str(TARGET_FC))
        assert os.path.exists(buffer.path)  # Проверяем, что директория создана

    def test_flush(self, loaded_frame_buffer):
        """Проверка очистки буфера."""
        loaded_frame_buffer.flush()

        assert loaded_frame_buffer._source_name is None
        assert loaded_frame_buffer._target_name is None
        assert loaded_frame_buffer._frames_count == 0
        assert loaded_frame_buffer._loaded is False
        assert loaded_frame_buffer._indices == []


class TestFrameDirectoryBufferFrameManagement:
    """Тесты для управления кадрами с использованием реальных файлов."""

    def test_add_frame_real_file(self, loaded_frame_buffer, sample_frame):
        """Проверка добавления кадра с записью в реальный файл."""
        loaded_frame_buffer.add_frame(sample_frame)

        # Проверяем наличие индекса
        assert 1 in loaded_frame_buffer._indices

        # Проверяем, что файл был создан

        filename = str(1).zfill(loaded_frame_buffer.zfill_length) + loaded_frame_buffer._writer.extension
        filepath = os.path.join(loaded_frame_buffer.path, filename)
        assert os.path.exists(filepath)

    def test_get_frame_real_file(self, loaded_frame_buffer, sample_frame):
        """Проверка получения кадра из реального файла."""
        # Добавляем кадр для создания реального файла
        loaded_frame_buffer.add_frame(sample_frame)

        # Получаем кадр
        frame = loaded_frame_buffer.get_frame(1)

        assert frame is not None
        assert frame.index == 1
        assert loaded_frame_buffer._miss == 0

        # Проверяем, что кадр имеет правильную форму
        assert frame.frame.shape == sample_frame.frame.shape

    def test_get_frame_previous_real(self, loaded_frame_buffer, sample_frame):
        """Проверка получения предыдущего кадра при отсутствии запрошенного."""
        # Создаем кадр с индексом 5
        frame5 = NumberedFrame(5, sample_frame.frame)

        # Добавляем кадр для создания реального файла
        loaded_frame_buffer.add_frame(frame5)

        # Пытаемся получить кадр 10, которого нет - должен вернуться кадр 5
        frame = loaded_frame_buffer.get_frame(10)

        assert frame is not None
        assert frame.index == 5
        assert loaded_frame_buffer._miss == 5  # 10 - 5 = 5

    def test_has_index_real(self, loaded_frame_buffer):
        """Проверка метода has_index с реальными индексами."""
        # Добавляем индексы для тестирования
        indices = [1, 5, 10]
        for index in indices:
            loaded_frame_buffer.add_index(index)

        assert loaded_frame_buffer.has_index(5) is True
        assert loaded_frame_buffer.has_index(7) is False
        assert loaded_frame_buffer.has_index(10) is True

    def test_init_indices_real(self, loaded_frame_buffer, sample_frame):
        """Проверка инициализации индексов из директории с реальными файлами."""
        # Создаем несколько тестовых кадров
        frames = [
            NumberedFrame(1, sample_frame.frame),
            NumberedFrame(3, sample_frame.frame),
            NumberedFrame(5, sample_frame.frame)
        ]

        # Добавляем кадры для создания реальных файлов
        for frame in frames:
            loaded_frame_buffer.add_frame(frame)

        # Очищаем список индексов
        loaded_frame_buffer._indices = []

        # Инициализируем индексы заново
        loaded_frame_buffer.init_indices()

        # Проверяем, что индексы были корректно прочитаны из файлов
        assert sorted(loaded_frame_buffer._indices) == [1, 3, 5]


class TestFrameDirectoryBufferThreadSafety:
    """Тесты на потокобезопасность с реальными файлами."""

    def test_thread_safety_add_frame_real(self, loaded_frame_buffer, sample_frame):
        """Проверка потокобезопасности при одновременном добавлении кадров."""
        # Создаем несколько кадров с разными индексами
        frames = [NumberedFrame(i, sample_frame.frame) for i in range(1, 11)]

        # Функция для добавления кадра в отдельном потоке
        def add_frame_thread(frame):
            loaded_frame_buffer.add_frame(frame)

        # Запускаем потоки
        threads = [threading.Thread(target=add_frame_thread, args=(frame,)) for frame in frames]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Проверяем, что все индексы были добавлены
        for i in range(1, 11):
            assert i in loaded_frame_buffer._indices

        # Проверяем, что файлы были созданы
        filename = str(i).zfill(loaded_frame_buffer.zfill_length) + loaded_frame_buffer._writer.extension
        filepath = os.path.join(loaded_frame_buffer.path, filename)
        assert os.path.exists(filepath)


class TestImprovements:
    """Тесты для проверки предлагаемых улучшений."""

    def test_has_index_with_rlock(self, loaded_frame_buffer):
        """Проверка метода has_index с использованием RLock."""
        # Добавляем индексы для тестирования
        loaded_frame_buffer._indices = [1, 5, 10]

        # Проверяем работу метода (уже защищенного RLock)

        assert loaded_frame_buffer.has_index(5) is True
        assert loaded_frame_buffer.has_index(7) is False

    def test_get_indices_returns_copy(self, loaded_frame_buffer):
        """Проверка, что get_indices возвращает копию списка."""
        # Добавляем индексы для тестирования
        loaded_frame_buffer._indices = [1, 5, 10]

        # Получаем индексы и проверяем, что это копия

        indices = loaded_frame_buffer.get_indices()
        assert indices == [1, 5, 10]

        # Проверяем, что изменение возвращенного списка не влияет на оригинал
        indices.append(15)
        assert loaded_frame_buffer._indices == [1, 5, 10]


class TestIntegration:
    """Интеграционные тесты для проверки взаимодействия методов."""

    def test_add_get_flow(self, loaded_frame_buffer, sample_frame):
        """Проверка полного цикла добавления и получения кадров."""
        # Добавляем кадры
        for i in range(1, 6):
            frame = NumberedFrame(i, sample_frame.frame)
            loaded_frame_buffer.add_frame(frame)

        # Получаем существующий кадр
        frame = loaded_frame_buffer.get_frame(3)
        assert frame is not None
        assert frame.index == 3

        # Получаем несуществующий кадр - должен вернуть предыдущий
        frame = loaded_frame_buffer.get_frame(8)
        assert frame is not None
        assert frame.index == 5  # последний добавленный
        assert loaded_frame_buffer._miss == 3  # 8 - 5 = 3

        # Получаем кадр за пределами начала - должен вернуть None
        frame = loaded_frame_buffer.get_frame(0, return_previous=False)
        assert frame is None

    def test_init_indices_and_get_frame(self, loaded_frame_buffer, sample_frame):
        """Проверка инициализации индексов и последующего получения кадров."""
        # Добавляем кадры
        for i in range(1, 6):
            frame = NumberedFrame(i, sample_frame.frame)
            loaded_frame_buffer.add_frame(frame)

        # Очищаем список индексов и инициализируем заново
        loaded_frame_buffer._indices = []

        loaded_frame_buffer.init_indices()

        # Проверяем, что индексы были корректно восстановлены
        assert sorted(loaded_frame_buffer._indices) == [1, 2, 3, 4, 5]

        # Получаем кадр
        frame = loaded_frame_buffer.get_frame(3)
        assert frame is not None
        assert frame.index == 3
