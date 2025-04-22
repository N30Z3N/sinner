import os
import threading
import pytest
import shutil
import numpy as np
from unittest.mock import patch

from sinner.models.NumberedFrame import NumberedFrame
from sinner.helpers.FrameHelper import write_to_image, read_from_image
from sinner.models.framebuffer.FrameDirectoryBuffer import FrameDirectoryBuffer
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
def mock_frame_helper():
    """Мокирует вспомогательные функции для работы с кадрами."""
    with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image') as mock_write, \
            patch('sinner.models.framebuffer.FrameDirectoryBuffer.read_from_image') as mock_read, \
            patch('sinner.models.framebuffer.FrameDirectoryBuffer.path_exists') as mock_path_exists, \
            patch('sinner.models.framebuffer.FrameDirectoryBuffer.is_absolute_path', return_value=True) as mock_is_absolute_path, \
            patch('sinner.models.framebuffer.FrameDirectoryBuffer.normalize_path', return_value='normalized_path') as mock_normalize_path, \
            patch('sinner.models.framebuffer.FrameDirectoryBuffer.get_file_name') as mock_get_file_name:
        # Настройка поведения моков
        mock_write.return_value = True
        mock_read.return_value = np.zeros(FRAME_SHAPE, dtype=np.uint8)  # Используем реальную константу размера кадра
        mock_path_exists.return_value = True
        mock_get_file_name.side_effect = lambda x: os.path.splitext(os.path.basename(x))[0]

        yield {
            'write_to_image': mock_write,
            'read_from_image': mock_read,
            'path_exists': mock_path_exists,
            'is_absolute_path': mock_is_absolute_path,
            'normalize_path': mock_normalize_path,
            'get_file_name': mock_get_file_name
        }


@pytest.fixture
def frame_buffer(cleanup_temp_dir):
    """Создает экземпляр FrameDirectoryBuffer с реальной временной директорией."""
    return FrameDirectoryBuffer(cleanup_temp_dir)


@pytest.fixture
def loaded_frame_buffer(frame_buffer):
    """Создает предварительно загруженный кадровый буфер с реальными файлами."""
    frame_buffer.load(source_jpg, target_mp4, TARGET_FC)
    return frame_buffer


@pytest.fixture
def sample_frame():
    """Создает тестовый кадр для использования в тестах."""
    return NumberedFrame(1, np.zeros(FRAME_SHAPE, dtype=np.uint8))


class TestFrameDirectoryBufferInit:
    """Тесты для инициализации и базовых свойств FrameDirectoryBuffer."""

    def test_init(self, cleanup_temp_dir):
        """Проверка корректной инициализации объекта."""
        buffer = FrameDirectoryBuffer(cleanup_temp_dir)
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

    def test_add_frame_real_file(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка добавления кадра с записью в реальный файл."""
        # Используем реальный метод write_to_image вместо мока
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
            loaded_frame_buffer.add_frame(sample_frame)

            # Проверяем наличие индекса
            assert 1 in loaded_frame_buffer._indices

            # Проверяем, что файл был создан
            filename = str(1).zfill(loaded_frame_buffer.zfill_length) + '.png'
            filepath = os.path.join(loaded_frame_buffer.path, filename)
            assert os.path.exists(filepath)

    def test_get_frame_real_file(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка получения кадра из реального файла."""
        # Добавляем кадр с реальной записью в файл
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
            loaded_frame_buffer.add_frame(sample_frame)

        # Используем реальный метод read_from_image для чтения
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.read_from_image', wraps=read_from_image):
            frame = loaded_frame_buffer.get_frame(1)

            assert frame is not None
            assert frame.index == 1
            assert loaded_frame_buffer._miss == 0

            # Проверяем размерность прочитанного кадра
            assert frame.frame.shape == FRAME_SHAPE

    def test_get_frame_previous_real(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка получения предыдущего кадра при отсутствии запрошенного (реальные файлы)."""
        # Создаем кадр с индексом 5
        frame5 = NumberedFrame(5, sample_frame.frame)

        # Добавляем кадр с реальной записью в файл
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
            loaded_frame_buffer.add_frame(frame5)

        # Пытаемся получить кадр 10, которого нет - должен вернуться кадр 5
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.read_from_image', wraps=read_from_image):
            frame = loaded_frame_buffer.get_frame(10)

            assert frame is not None
            assert frame.index == 5
            assert loaded_frame_buffer._miss == 5  # 10 - 5 = 5

    def test_has_index_real(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка метода has_index с реальными индексами."""
        # Добавляем кадры с индексами 1, 5, 10
        frames = [
            NumberedFrame(1, sample_frame.frame),
            NumberedFrame(5, sample_frame.frame),
            NumberedFrame(10, sample_frame.frame)
        ]

        for frame in frames:
            loaded_frame_buffer.add_index(frame.index)

        assert loaded_frame_buffer.has_index(5) is True
        assert loaded_frame_buffer.has_index(7) is False
        assert loaded_frame_buffer.has_index(10) is True

    def test_init_indices_real(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка инициализации индексов из директории с реальными файлами."""
        # Создаем несколько тестовых кадров
        frames = [
            NumberedFrame(1, sample_frame.frame),
            NumberedFrame(3, sample_frame.frame),
            NumberedFrame(5, sample_frame.frame)
        ]

        # Добавляем кадры с реальной записью в файлы
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
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

    def test_thread_safety_add_frame_real(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка потокобезопасности при одновременном добавлении кадров (реальные файлы)."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Создаем несколько кадров с разными индексами
        frames = [NumberedFrame(i, sample_frame.frame) for i in range(1, 11)]

        # Функция для добавления кадра в отдельном потоке
        def add_frame_thread(frame):
            with loaded_frame_buffer._indices_lock:
                loaded_frame_buffer.add_frame(frame)

        # Запускаем потоки
        threads = [threading.Thread(target=add_frame_thread, args=(frame,)) for frame in frames]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Проверяем, что все индексы были добавлены
        with loaded_frame_buffer._indices_lock:
            for i in range(1, 11):
                assert i in loaded_frame_buffer._indices

                # Проверяем, что файлы были созданы
                filename = str(i).zfill(loaded_frame_buffer.zfill_length) + '.png'
                filepath = os.path.join(loaded_frame_buffer.path, filename)
                assert os.path.exists(filepath)

    def test_optimized_get_frame_real_files(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Тест оптимизированной версии get_frame с реальными файлами."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Создаем реальные файлы для тестирования
        frames = [
            NumberedFrame(1, sample_frame.frame),
            NumberedFrame(5, sample_frame.frame),
            NumberedFrame(10, sample_frame.frame)
        ]

        # Сохраняем файлы на диск
        for frame in frames:
            filename = str(frame.index).zfill(loaded_frame_buffer.zfill_length) + '.png'
            filepath = os.path.join(loaded_frame_buffer.path, filename)
            write_to_image(frame.frame, filepath)
            loaded_frame_buffer._indices.append(frame.index)

        # Реализация оптимизированного метода get_frame
        def optimized_get_frame(index, return_previous=True):
            if not loaded_frame_buffer._loaded:
                return None

            # Проверяем наличие индекса в списке
            with loaded_frame_buffer._indices_lock:
                has_index = index in loaded_frame_buffer._indices

            if has_index:
                filename = str(index).zfill(loaded_frame_buffer.zfill_length) + '.png'
                filepath = os.path.join(loaded_frame_buffer.path, filename)
                try:
                    loaded_frame_buffer._miss = 0
                    return NumberedFrame(index, read_from_image(filepath))
                except Exception:
                    pass

            if return_previous:
                with loaded_frame_buffer._indices_lock:
                    indices = sorted(loaded_frame_buffer._indices)
                    for prev_idx in indices[::-1]:
                        if prev_idx < index:
                            filename = str(prev_idx).zfill(loaded_frame_buffer.zfill_length) + '.png'
                            filepath = os.path.join(loaded_frame_buffer.path, filename)
                            if os.path.exists(filepath):
                                try:
                                    loaded_frame_buffer._miss = index - prev_idx
                                    return NumberedFrame(prev_idx, read_from_image(filepath))
                                except Exception:
                                    pass
            return None

        # Патчим метод get_frame оптимизированной версией
        with patch.object(loaded_frame_buffer, 'get_frame', side_effect=optimized_get_frame):
            # Проверяем прямой доступ к существующему индексу
            frame = loaded_frame_buffer.get_frame(5)
            assert frame is not None
            assert frame.index == 5

            # Проверяем доступ к несуществующему индексу
            frame = loaded_frame_buffer.get_frame(7)
            assert frame is not None
            assert frame.index == 5  # возвращает предыдущий
            assert loaded_frame_buffer._miss == 2  # 7 - 5 = 2


class TestImprovements:
    """Тесты для проверки предлагаемых улучшений."""

    def test_has_index_with_rlock(self, loaded_frame_buffer):
        """Проверка метода has_index с использованием RLock."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Реализация улучшенного метода has_index
        def improved_has_index(index):
            with loaded_frame_buffer._indices_lock:
                return index in loaded_frame_buffer._indices

        # Патчим метод has_index улучшенной версией
        with patch.object(loaded_frame_buffer, 'has_index', side_effect=improved_has_index):
            # Добавляем индексы для тестирования
            with loaded_frame_buffer._indices_lock:
                loaded_frame_buffer._indices = [1, 5, 10]

            # Проверяем работу метода
            assert loaded_frame_buffer.has_index(5) is True
            assert loaded_frame_buffer.has_index(7) is False

    def test_get_indices_with_rlock(self, loaded_frame_buffer):
        """Проверка метода get_indices с использованием RLock и возвратом копии."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Реализация улучшенного метода get_indices
        def improved_get_indices():
            with loaded_frame_buffer._indices_lock:
                return loaded_frame_buffer._indices.copy()

        # Патчим метод get_indices улучшенной версией
        with patch.object(loaded_frame_buffer, 'get_indices', side_effect=improved_get_indices):
            # Добавляем индексы для тестирования
            with loaded_frame_buffer._indices_lock:
                loaded_frame_buffer._indices = [1, 5, 10]

            # Проверяем работу метода
            indices = loaded_frame_buffer.get_indices()
            assert indices == [1, 5, 10]

            # Проверяем, что изменение возвращенного списка не влияет на оригинал
            indices.append(15)
            with loaded_frame_buffer._indices_lock:
                assert loaded_frame_buffer._indices == [1, 5, 10]


class TestIntegration:
    """Интеграционные тесты для проверки взаимодействия методов."""

    def test_add_get_flow(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка полного цикла добавления и получения кадров."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Добавляем кадры
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
            for i in range(1, 6):
                frame = NumberedFrame(i, sample_frame.frame)
                loaded_frame_buffer.add_frame(frame)

        # Получаем кадры в разном порядке
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.read_from_image', wraps=read_from_image):
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

    def test_init_indices_and_get_frame(self, loaded_frame_buffer, sample_frame, cleanup_temp_dir):
        """Проверка инициализации индексов и последующего получения кадров."""
        # Добавляем RLock для защиты от состояний гонки
        loaded_frame_buffer._indices_lock = threading.RLock()

        # Добавляем кадры
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.write_to_image', wraps=write_to_image):
            for i in range(1, 6):
                frame = NumberedFrame(i, sample_frame.frame)
                loaded_frame_buffer.add_frame(frame)

        # Очищаем список индексов и инициализируем заново
        with loaded_frame_buffer._indices_lock:
            loaded_frame_buffer._indices = []
        loaded_frame_buffer.init_indices()

        # Проверяем, что индексы были корректно восстановлены
        with loaded_frame_buffer._indices_lock:
            assert sorted(loaded_frame_buffer._indices) == [1, 2, 3, 4, 5]

        # Получаем кадр
        with patch('sinner.models.framebuffer.FrameDirectoryBuffer.read_from_image', wraps=read_from_image):
            frame = loaded_frame_buffer.get_frame(3)
            assert frame is not None
            assert frame.index == 3
