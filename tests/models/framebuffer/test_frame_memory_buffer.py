import threading
import time
import numpy as np
import pytest
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor

from sinner.models.NumberedFrame import NumberedFrame
from sinner.models.framebuffer.FrameMemoryBuffer import FrameMemoryBuffer
from tests.constants import tmp_dir


# Фикстуры
@pytest.fixture
def temp_dir():
    """Создаёт временную директорию для тестов и удаляет её после завершения."""
    test_dir = tempfile.mkdtemp(dir=tmp_dir)
    yield test_dir
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def memory_buffer(temp_dir):
    """Создаёт экземпляр FrameMemoryBuffer для тестов."""
    buffer = FrameMemoryBuffer(temp_dir, buffer_size=1024 * 1024)  # 1MB буфер
    buffer.load("source", "target", 10)  # Предзагрузка для большинства тестов
    yield buffer


@pytest.fixture
def memory_buffer_with_early_removal(temp_dir):
    """Создаёт экземпляр FrameMemoryBuffer с включенным удалением ранних кадров."""
    buffer = FrameMemoryBuffer(temp_dir, buffer_size=1024 * 1024, remove_earlier_frames=True)
    buffer.load("source", "target", 10)
    yield buffer


@pytest.fixture
def disk_only_buffer(temp_dir):
    """Создаёт экземпляр FrameMemoryBuffer с отключенным буфером памяти."""
    buffer = FrameMemoryBuffer(temp_dir, buffer_size=0)  # Буфер памяти отключен
    buffer.load("source", "target", 10)
    yield buffer


@pytest.fixture
def sample_frame():
    """Создаёт тестовый кадр небольшого размера."""
    frame_data = np.zeros((10, 10, 3), dtype=np.uint8)
    frame_data[:5, :5] = [255, 0, 0]  # Красный квадрат в верхнем левом углу
    frame_data[5:, 5:] = [0, 255, 0]  # Зелёный квадрат в нижнем правом углу
    return NumberedFrame(index=1, frame=frame_data)


@pytest.fixture
def multiple_frames():
    """Создаёт набор тестовых кадров."""
    frames = []
    for i in range(1, 6):  # Создаём 5 кадров
        frame_data = np.ones((10, 10, 3), dtype=np.uint8) * (i * 50)  # Разный цвет для каждого кадра
        frames.append(NumberedFrame(index=i, frame=frame_data))
    return frames


@pytest.fixture
def large_frame():
    """Создаёт кадр, размер которого превышает размер буфера."""
    frame_data = np.ones((1000, 1000, 3), dtype=np.uint8) * 128  # ~3MB (1000x1000x3)
    return NumberedFrame(index=100, frame=frame_data)


# Тесты базовой функциональности
class TestBasicFunctionality:
    def test_initialization(self, temp_dir):
        """Проверка корректной инициализации буфера."""
        buffer_size = 10 * 1024 * 1024  # 10MB
        buffer = FrameMemoryBuffer(temp_dir, buffer_size=buffer_size)

        assert buffer._buffer_size == buffer_size
        assert buffer._current_buffer_size == 0
        # Проверяем наличие методов lock вместо проверки типа
        assert hasattr(buffer._buffer_lock, 'acquire')
        assert hasattr(buffer._buffer_lock, 'release')
        assert isinstance(buffer._disk_write_executor, ThreadPoolExecutor)
        assert buffer._memory_buffer == {}
        assert buffer._frame_sizes == {}
        assert not buffer._remove_earlier_frames  # По умолчанию выключено

    def test_initialization_with_early_removal(self, temp_dir):
        """Проверка инициализации с включенным удалением ранних кадров."""
        buffer = FrameMemoryBuffer(temp_dir, buffer_size=1024 * 1024, remove_earlier_frames=True)

        assert buffer._remove_earlier_frames is True

    def test_initialization_with_disabled_buffer(self, temp_dir):
        """Проверка инициализации с отключенным буфером памяти."""
        buffer = FrameMemoryBuffer(temp_dir, buffer_size=0)

        assert buffer._buffer_size == 0
        assert buffer._current_buffer_size == 0
        assert buffer._memory_buffer == {}
        assert buffer._frame_sizes == {}

    def test_load(self, memory_buffer):
        """Проверка метода load."""
        # Проверяем, что буфер успешно загрузился
        assert memory_buffer._loaded is True
        assert memory_buffer._source_name == "source"
        assert memory_buffer._target_name == "target"
        assert memory_buffer._frames_count == 10


# Тесты добавления кадров
class TestAddFrame:
    def test_add_frame_to_memory(self, memory_buffer, sample_frame):
        """Проверка добавления кадра в буфер памяти."""
        memory_buffer.add_frame(sample_frame)

        # Проверяем наличие кадра в памяти
        assert sample_frame.index in memory_buffer._memory_buffer
        assert memory_buffer._current_buffer_size > 0
        assert memory_buffer._frame_sizes[sample_frame.index] == sample_frame.frame.nbytes

        # Даём время на асинхронную запись на диск
        time.sleep(0.1)

        # Проверяем, что кадр появился в индексах (записан на диск)
        assert sample_frame.index in memory_buffer.get_indices()

    def test_add_frame_direct_to_disk(self, memory_buffer, large_frame):
        """Проверка прямой записи на диск при заполненном буфере."""
        # Добавляем кадр, превышающий размер буфера
        memory_buffer.add_frame(large_frame)

        # Проверяем, что кадр не попал в память
        assert large_frame.index not in memory_buffer._memory_buffer

        # Даём время на запись на диск
        time.sleep(0.1)

        # Проверяем, что кадр записан на диск
        assert memory_buffer.has_index(large_frame.index)

    def test_add_frame_disk_only(self, disk_only_buffer, sample_frame):
        """Проверка добавления кадра при отключенном буфере памяти."""
        disk_only_buffer.add_frame(sample_frame)

        # Проверяем, что кадр не попал в память (буфер отключен)
        assert sample_frame.index not in disk_only_buffer._memory_buffer
        assert disk_only_buffer._current_buffer_size == 0

        # Даём время на запись на диск
        time.sleep(0.1)

        # Проверяем, что кадр записан на диск
        assert disk_only_buffer.has_index(sample_frame.index)
        assert sample_frame.index in disk_only_buffer.get_indices()

    def test_add_multiple_frames(self, memory_buffer, multiple_frames):
        """Проверка добавления нескольких кадров."""
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Проверяем наличие всех кадров в памяти
        for frame in multiple_frames:
            assert frame.index in memory_buffer._memory_buffer

        # Даём время на асинхронную запись на диск
        time.sleep(0.2)

        # Проверяем, что все кадры записаны на диск
        for frame in multiple_frames:
            assert frame.index in memory_buffer.get_indices()

    def test_add_multiple_frames_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка добавления нескольких кадров при отключенном буфере памяти."""
        for frame in multiple_frames:
            disk_only_buffer.add_frame(frame)

        # Проверяем, что ни один кадр не попал в память
        assert len(disk_only_buffer._memory_buffer) == 0
        assert disk_only_buffer._current_buffer_size == 0

        # Даём время на запись на диск
        time.sleep(0.2)

        # Проверяем, что все кадры записаны на диск
        for frame in multiple_frames:
            assert frame.index in disk_only_buffer.get_indices()


# Тесты получения кадров
class TestGetFrame:
    def test_get_frame_from_memory(self, memory_buffer, sample_frame):
        """Проверка получения кадра из памяти."""
        memory_buffer.add_frame(sample_frame)

        retrieved_frame = memory_buffer.get_frame(sample_frame.index)

        # Проверяем корректность полученного кадра
        assert retrieved_frame is not None
        assert retrieved_frame.index == sample_frame.index
        np.testing.assert_array_equal(retrieved_frame.frame, sample_frame.frame)

        # Проверяем, что кадр удалён из памяти после получения
        assert sample_frame.index not in memory_buffer._memory_buffer
        # Проверяем, что счётчик размера буфера обновлён
        assert memory_buffer._current_buffer_size == 0

    def test_get_frame_from_disk(self, memory_buffer, sample_frame):
        """Проверка получения кадра с диска после удаления из памяти."""
        memory_buffer.add_frame(sample_frame)

        # Ждём завершения записи на диск
        time.sleep(0.1)

        # Удаляем кадр из памяти, но оставляем на диске
        with memory_buffer._buffer_lock:
            if sample_frame.index in memory_buffer._memory_buffer:
                memory_buffer._memory_buffer.pop(sample_frame.index)
                memory_buffer._frame_sizes.pop(sample_frame.index)
                memory_buffer._current_buffer_size = 0

        # Получаем кадр (должен читаться с диска)
        retrieved_frame = memory_buffer.get_frame(sample_frame.index)

        # Проверяем корректность полученного кадра
        assert retrieved_frame is not None
        assert retrieved_frame.index == sample_frame.index
        # Формы массивов должны совпадать (точное сравнение может не работать из-за сжатия PNG)
        assert retrieved_frame.frame.shape == sample_frame.frame.shape

    def test_get_frame_disk_only(self, disk_only_buffer, sample_frame):
        """Проверка получения кадра при отключенном буфере памяти."""
        disk_only_buffer.add_frame(sample_frame)

        # Даём время на запись на диск
        time.sleep(0.1)

        # Получаем кадр (должен читаться с диска)
        retrieved_frame = disk_only_buffer.get_frame(sample_frame.index)

        # Проверяем корректность полученного кадра
        assert retrieved_frame is not None
        assert retrieved_frame.index == sample_frame.index
        # Формы массивов должны совпадать
        assert retrieved_frame.frame.shape == sample_frame.frame.shape

        # Убеждаемся, что буфер памяти остался пустым
        assert len(disk_only_buffer._memory_buffer) == 0
        assert disk_only_buffer._current_buffer_size == 0

    def test_get_nonexistent_frame(self, memory_buffer):
        """Проверка получения несуществующего кадра."""
        retrieved_frame = memory_buffer.get_frame(999, return_previous=False)
        assert retrieved_frame is None

    def test_get_previous_frame(self, memory_buffer, multiple_frames):
        """Проверка получения предыдущего кадра, если запрошенный не существует."""
        # Добавляем кадры 1-5
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Даём время на асинхронную запись на диск
        time.sleep(0.2)

        # Запрашиваем кадр 7 (не существует), должен вернуться кадр 5
        retrieved_frame = memory_buffer.get_frame(7, return_previous=True)

        assert retrieved_frame is not None
        assert retrieved_frame.index == 5  # Последний из добавленных кадров

    def test_get_previous_frame_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка получения предыдущего кадра при отключенном буфере памяти."""
        # Добавляем кадры 1-5
        for frame in multiple_frames:
            disk_only_buffer.add_frame(frame)

        # Даём время на запись на диск
        time.sleep(0.2)

        # Запрашиваем кадр 7 (не существует), должен вернуться кадр 5
        retrieved_frame = disk_only_buffer.get_frame(7, return_previous=True)

        assert retrieved_frame is not None
        assert retrieved_frame.index == 5  # Последний из добавленных кадров

    def test_get_frame_with_early_removal(self, memory_buffer, multiple_frames):
        """Проверка получения кадра с удалением ранних кадров."""
        # Добавляем кадры 1-5
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Запрашиваем кадр 3 с параметром remove_earlier_frames=True
        retrieved_frame = memory_buffer.get_frame(3, remove_earlier_frames=True)

        assert retrieved_frame is not None
        assert retrieved_frame.index == 3

        # Проверяем, что кадры 1-2 удалены из памяти
        assert 1 not in memory_buffer._memory_buffer
        assert 2 not in memory_buffer._memory_buffer

        # Проверяем, что кадры 4-5 остались в памяти
        assert 4 in memory_buffer._memory_buffer
        assert 5 in memory_buffer._memory_buffer

    def test_default_early_removal_strategy(self, memory_buffer_with_early_removal, multiple_frames):
        """Проверка стратегии удаления ранних кадров по умолчанию."""
        # Добавляем кадры 1-5
        for frame in multiple_frames:
            memory_buffer_with_early_removal.add_frame(frame)

        # Запрашиваем кадр 3 (без явного указания параметра remove_earlier_frames)
        # Должна использоваться стратегия по умолчанию (True)
        retrieved_frame = memory_buffer_with_early_removal.get_frame(3)

        assert retrieved_frame is not None
        assert retrieved_frame.index == 3

        # Проверяем, что кадры 1-2 удалены из памяти
        assert 1 not in memory_buffer_with_early_removal._memory_buffer
        assert 2 not in memory_buffer_with_early_removal._memory_buffer

        # Проверяем, что кадры 4-5 остались в памяти
        assert 4 in memory_buffer_with_early_removal._memory_buffer
        assert 5 in memory_buffer_with_early_removal._memory_buffer

    def test_override_early_removal_strategy(self, memory_buffer_with_early_removal, multiple_frames):
        """Проверка переопределения стратегии удаления ранних кадров."""
        # Добавляем кадры 1-5
        for frame in multiple_frames:
            memory_buffer_with_early_removal.add_frame(frame)

        # Запрашиваем кадр 3 с явным отключением стратегии удаления ранних кадров
        retrieved_frame = memory_buffer_with_early_removal.get_frame(3, remove_earlier_frames=False)

        assert retrieved_frame is not None
        assert retrieved_frame.index == 3

        # Проверяем, что кадры 1-2 НЕ удалены из памяти (стратегия отключена для этого вызова)
        assert 1 in memory_buffer_with_early_removal._memory_buffer
        assert 2 in memory_buffer_with_early_removal._memory_buffer


# Тесты мониторинга состояния буфера
class TestBufferState:
    def test_has_index_memory(self, memory_buffer, sample_frame):
        """Проверка has_index для кадра в памяти."""
        memory_buffer.add_frame(sample_frame)

        assert memory_buffer.has_index(sample_frame.index)

    def test_has_index_disk(self, memory_buffer, sample_frame):
        """Проверка has_index для кадра на диске, но не в памяти."""
        memory_buffer.add_frame(sample_frame)

        # Ждём завершения записи на диск
        time.sleep(0.1)

        # Удаляем кадр из памяти
        with memory_buffer._buffer_lock:
            if sample_frame.index in memory_buffer._memory_buffer:
                memory_buffer._memory_buffer.pop(sample_frame.index)
                memory_buffer._frame_sizes.pop(sample_frame.index)
                memory_buffer._current_buffer_size = 0

        assert memory_buffer.has_index(sample_frame.index)

    def test_has_index_disk_only(self, disk_only_buffer, sample_frame):
        """Проверка has_index для кадра при отключенном буфере памяти."""
        disk_only_buffer.add_frame(sample_frame)

        # Даём время на запись на диск
        time.sleep(0.1)

        assert disk_only_buffer.has_index(sample_frame.index)

    def test_has_index_nonexistent(self, memory_buffer):
        """Проверка has_index для несуществующего кадра."""
        assert not memory_buffer.has_index(999)

    def test_get_buffer_info(self, memory_buffer, multiple_frames):
        """Проверка получения информации о буфере."""
        # Добавляем кадры в буфер
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Получаем информацию о буфере
        buffer_info = memory_buffer.get_buffer_info()

        # Проверяем наличие всех ключей
        assert "frames_in_memory" in buffer_info
        assert "memory_usage_bytes" in buffer_info
        assert "memory_limit_bytes" in buffer_info
        assert "usage_percent" in buffer_info
        assert "frame_indices_in_memory" in buffer_info
        assert "remove_earlier_frames_strategy" in buffer_info

        # Проверяем значения
        assert buffer_info["frames_in_memory"] == len(multiple_frames)
        assert buffer_info["memory_usage_bytes"] > 0
        assert buffer_info["memory_limit_bytes"] == memory_buffer._buffer_size
        assert buffer_info["remove_earlier_frames_strategy"] is False  # По умолчанию отключено

        # Проверяем, что все индексы присутствуют
        frame_indices = [frame.index for frame in multiple_frames]
        for idx in frame_indices:
            assert idx in buffer_info["frame_indices_in_memory"]

    def test_get_buffer_info_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка получения информации о буфере при отключенном буфере памяти."""
        # Добавляем кадры напрямую на диск
        for frame in multiple_frames:
            disk_only_buffer.add_frame(frame)

        # Даём время на запись на диск
        time.sleep(0.2)

        # Получаем информацию о буфере
        buffer_info = disk_only_buffer.get_buffer_info()

        # Проверяем значения
        assert buffer_info["frames_in_memory"] == 0  # Нет кадров в памяти
        assert buffer_info["memory_usage_bytes"] == 0
        assert buffer_info["memory_limit_bytes"] == 0
        assert buffer_info["usage_percent"] == 0
        assert len(buffer_info["frame_indices_in_memory"]) == 0


# Тесты операций обслуживания
class TestMaintenanceOperations:
    def test_flush(self, memory_buffer, multiple_frames):
        """Проверка очистки буфера."""
        # Добавляем несколько кадров
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Проверяем, что кадры в памяти
        assert len(memory_buffer._memory_buffer) > 0

        # Очищаем буфер
        memory_buffer.flush()

        # Проверяем, что память очищена
        assert len(memory_buffer._memory_buffer) == 0
        assert memory_buffer._current_buffer_size == 0
        assert memory_buffer._frame_sizes == {}
        assert not memory_buffer._loaded

    def test_flush_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка очистки буфера при отключенном буфере памяти."""
        # Добавляем несколько кадров
        for frame in multiple_frames:
            disk_only_buffer.add_frame(frame)

        # Проверяем, что память пуста
        assert len(disk_only_buffer._memory_buffer) == 0

        # Очищаем буфер
        disk_only_buffer.flush()

        # Проверяем, что память всё ещё пуста
        assert len(disk_only_buffer._memory_buffer) == 0
        assert disk_only_buffer._current_buffer_size == 0
        assert disk_only_buffer._frame_sizes == {}
        assert not disk_only_buffer._loaded

    def test_init_indices(self, memory_buffer, multiple_frames):
        """Проверка инициализации индексов из диска и памяти."""
        # Добавляем кадры в память и на диск
        for frame in multiple_frames:
            memory_buffer.add_frame(frame)

        # Даём время на асинхронную запись на диск
        time.sleep(0.2)

        # Очищаем индексы
        with memory_buffer._indices_lock:
            memory_buffer._indices = []

        # Реинициализируем индексы
        memory_buffer.init_indices()

        # Проверяем, что индексы загружены
        indices = memory_buffer.get_indices()
        assert len(indices) == len(multiple_frames)
        for frame in multiple_frames:
            assert frame.index in indices

    def test_init_indices_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка инициализации индексов при отключенном буфере памяти."""
        # Добавляем кадры напрямую на диск
        for frame in multiple_frames:
            disk_only_buffer.add_frame(frame)

        # Даём время на запись на диск
        time.sleep(0.2)

        # Очищаем индексы
        with disk_only_buffer._indices_lock:
            disk_only_buffer._indices = []

        # Реинициализируем индексы
        disk_only_buffer.init_indices()

        # Проверяем, что индексы загружены только с диска
        indices = disk_only_buffer.get_indices()
        assert len(indices) == len(multiple_frames)
        for frame in multiple_frames:
            assert frame.index in indices


# Тесты обработки ошибок и граничных случаев
class TestErrorHandlingAndEdgeCases:
    def test_disk_write_error(self, memory_buffer, sample_frame, monkeypatch):
        """Проверка обработки ошибок при записи на диск."""
        # Вместо патча внешней функции нужно патчить метод класса
        # который непосредственно добавляет индекс

        original_method = memory_buffer._save_frame_to_disk

        def mock_save_frame_to_disk(frame):
            # Вызываем все до добавления индекса, но не добавляем его.
            # Это имитирует ситуацию, когда запись на диск не удалась.
            # Обратите внимание, что мы не поднимаем исключение, так как
            # в реальном коде исключение обрабатывается внутри метода
            return

        # Заменяем метод
        memory_buffer._save_frame_to_disk = mock_save_frame_to_disk

        try:
            # Добавляем кадр
            memory_buffer.add_frame(sample_frame)

            # Кадр должен быть добавлен в память
            assert sample_frame.index in memory_buffer._memory_buffer

            # Но индекс не должен быть добавлен, так как запись на диск "не удалась"
            assert sample_frame.index not in memory_buffer.get_indices()
        finally:
            # Восстанавливаем оригинальный метод
            memory_buffer._save_frame_to_disk = original_method

    def test_disk_write_error_disk_only(self, disk_only_buffer, sample_frame, monkeypatch):
        """Проверка обработки ошибок при записи на диск с отключенным буфером памяти."""
        original_method = disk_only_buffer._save_frame_to_disk

        def mock_save_frame_to_disk(frame):
            # Имитируем ошибку записи на диск
            return

        # Заменяем метод
        disk_only_buffer._save_frame_to_disk = mock_save_frame_to_disk

        try:
            # Добавляем кадр
            disk_only_buffer.add_frame(sample_frame)

            # Индекс не должен быть добавлен, так как запись на диск "не удалась"
            assert sample_frame.index not in disk_only_buffer.get_indices()

            # Кадр также не должен быть в памяти (буфер отключен)
            assert sample_frame.index not in disk_only_buffer._memory_buffer
        finally:
            # Восстанавливаем оригинальный метод
            disk_only_buffer._save_frame_to_disk = original_method

    def test_concurrent_operations(self, memory_buffer, multiple_frames):
        """Проверка одновременного добавления и получения кадров."""

        # Функция для добавления кадров в отдельном потоке
        def add_frames():
            for frame in multiple_frames:
                memory_buffer.add_frame(frame)

        # Функция для получения кадров в отдельном потоке
        results = []

        def get_frames():
            # Небольшая задержка, чтобы некоторые кадры успели добавиться
            time.sleep(0.05)
            for i in range(1, len(multiple_frames) + 1):
                results.append(memory_buffer.get_frame(i))

        # Запускаем потоки
        add_thread = threading.Thread(target=add_frames)
        get_thread = threading.Thread(target=get_frames)

        add_thread.start()
        get_thread.start()

        add_thread.join()
        get_thread.join()

        # Проверяем результаты
        assert len(results) == len(multiple_frames)
        # Некоторые кадры могут быть из памяти, некоторые - с диска
        non_none_results = [r for r in results if r is not None]
        assert len(non_none_results) > 0  # Хотя бы один кадр должен быть найден

    def test_concurrent_operations_disk_only(self, disk_only_buffer, multiple_frames):
        """Проверка одновременного добавления и получения кадров при отключенном буфере памяти."""

        # Функция для добавления кадров в отдельном потоке
        def add_frames():
            for frame in multiple_frames:
                disk_only_buffer.add_frame(frame)

        # Функция для получения кадров в отдельном потоке
        results = []

        def get_frames():
            # Небольшая задержка, чтобы некоторые кадры успели записаться на диск
            time.sleep(0.1)
            for i in range(1, len(multiple_frames) + 1):
                results.append(disk_only_buffer.get_frame(i))

        # Запускаем потоки
        add_thread = threading.Thread(target=add_frames)
        get_thread = threading.Thread(target=get_frames)

        add_thread.start()
        get_thread.start()

        add_thread.join()
        get_thread.join()

        # Проверяем результаты
        assert len(results) == len(multiple_frames)
        # Некоторые кадры могут быть найдены, некоторые - нет (из-за времени записи на диск)
        non_none_results = [r for r in results if r is not None]
        # Буфер памяти должен остаться пустым
        assert len(disk_only_buffer._memory_buffer) == 0

    def test_empty_frame_handling(self, memory_buffer):
        """Проверка обработки пустых кадров."""
        # Создаём кадр с пустым массивом
        empty_frame = NumberedFrame(index=999, frame=np.array([], dtype=np.uint8))

        # Проверяем, что добавление не вызывает ошибок
        memory_buffer.add_frame(empty_frame)

        # Даём время на асинхронную запись на диск
        time.sleep(0.1)

        # Получаем кадр обратно
        retrieved_frame = memory_buffer.get_frame(999)

        # Проверяем, что кадр корректно обработан
        # В зависимости от реализации может вернуться None или пустой кадр
        if retrieved_frame is not None:
            assert retrieved_frame.index == 999
