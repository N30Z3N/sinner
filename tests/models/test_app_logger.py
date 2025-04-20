import logging
import os
import platform
import tempfile
from logging.handlers import SysLogHandler, TimedRotatingFileHandler, RotatingFileHandler
from unittest.mock import patch, Mock
import pytest

from colorama import Fore, Back, Style

from sinner.AppLogger import app_logger, LevelBasedFormatter, ColoredFormatter, add_handler, remove_handler, setup_logging


# Фикстуры для тестов
@pytest.fixture
def clean_logger():
    """Фикстура для сброса состояния логгера перед каждым тестом"""
    # Сохраняем оригинальные обработчики
    original_handlers = list(app_logger.handlers)
    original_level = app_logger.level

    # Очищаем логгер
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)

    yield  # Выполняем тест

    # Восстанавливаем логгер после теста
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)

    # Восстанавливаем оригинальные обработчики
    for handler in original_handlers:
        app_logger.addHandler(handler)

    app_logger.setLevel(original_level)


@pytest.fixture
def temp_log_file():
    """Фикстура для создания временного лог-файла"""
    fd, path = tempfile.mkstemp(suffix='.log')
    os.close(fd)
    yield path

    # Очищаем все обработчики перед попыткой удаления файла
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        if hasattr(handler, 'close'):
            handler.close()

    # Удаляем файл после теста с небольшой задержкой
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        import time
        time.sleep(0.1)  # Даем Windows время на освобождение файла
        if os.path.exists(path):
            os.remove(path)


# Тесты форматтеров
class TestFormatters:
    def test_level_based_formatter(self):
        """Тест форматирования в зависимости от уровня"""
        formats = {
            logging.DEBUG: 'DEBUG_FORMAT: %(message)s',
            logging.INFO: 'INFO_FORMAT: %(message)s',
            None: 'DEFAULT_FORMAT: %(message)s'
        }

        formatter = LevelBasedFormatter(formats)

        # Создаем тестовые записи логирования
        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG,
            pathname="", lineno=0, msg="Debug message",
            args=(), exc_info=None
        )

        info_record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="Info message",
            args=(), exc_info=None
        )

        warn_record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname="", lineno=0, msg="Warning message",
            args=(), exc_info=None
        )

        # Проверяем форматирование для разных уровней
        assert formatter.format(debug_record) == 'DEBUG_FORMAT: Debug message'
        assert formatter.format(info_record) == 'INFO_FORMAT: Info message'
        assert formatter.format(warn_record) == 'DEFAULT_FORMAT: Warning message'

    def test_colored_formatter(self):
        """Тест цветного форматирования"""
        formats = {
            logging.DEBUG: 'DEBUG: %(message)s',
            logging.INFO: 'INFO: %(message)s',
            None: 'DEFAULT: %(message)s'
        }

        formatter = ColoredFormatter(formats)

        # Создаем тестовую запись логирования
        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG,
            pathname="", lineno=0, msg="Debug message",
            args=(), exc_info=None
        )

        # Проверяем, что в отформатированной строке есть цветовая разметка
        formatted = formatter.format(debug_record)
        assert Fore.CYAN in formatted
        assert Back.BLACK in formatted
        assert Style.RESET_ALL in formatted
        assert 'DEBUG: Debug message' in formatted

    def test_default_formats(self):
        """Тест проверки формата по умолчанию"""
        from sinner.AppLogger import DEFAULT_FORMATS

        # Проверяем наличие форматов для всех уровней логирования
        assert logging.DEBUG in DEFAULT_FORMATS
        assert logging.INFO in DEFAULT_FORMATS
        assert logging.WARNING in DEFAULT_FORMATS
        assert logging.ERROR in DEFAULT_FORMATS
        assert logging.CRITICAL in DEFAULT_FORMATS
        assert None in DEFAULT_FORMATS

        # Проверяем содержимое форматов
        assert '%(module)s.%(funcName)s:%(lineno)d:' in DEFAULT_FORMATS[logging.DEBUG]
        assert '%(module)s:' in DEFAULT_FORMATS[logging.INFO]


# Тесты добавления/удаления обработчиков
class TestHandlers:
    def test_add_stdout_handler(self, clean_logger):
        """Тест добавления обработчика для stdout"""
        handler = add_handler('stdout')

        assert handler in app_logger.handlers
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, ColoredFormatter)

    def test_add_file_handler(self, clean_logger, temp_log_file):
        """Тест добавления файлового обработчика"""
        handler = add_handler('file', filename=temp_log_file)

        assert handler in app_logger.handlers
        assert isinstance(handler, logging.FileHandler)
        assert isinstance(handler.formatter, LevelBasedFormatter)
        assert handler.baseFilename == temp_log_file

    def test_add_rotating_file_handler(self, clean_logger, temp_log_file):
        """Тест добавления обработчика с ротацией по размеру"""
        handler = add_handler('rotating_file', filename=temp_log_file, maxBytes=1024, backupCount=3)

        assert handler in app_logger.handlers
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == 1024
        assert handler.backupCount == 3

    def test_add_timed_rotating_file_handler(self, clean_logger, temp_log_file):
        """Тест добавления обработчика с ротацией по времени"""
        handler = add_handler('timed_rotating_file', filename=temp_log_file, when='H', backupCount=5)

        assert handler in app_logger.handlers
        assert isinstance(handler, TimedRotatingFileHandler)
        assert handler.when == 'H'
        assert handler.backupCount == 5

    def test_handler_level(self, clean_logger):
        """Тест установки уровня логирования для обработчика"""
        handler = add_handler('stdout', level=logging.WARNING)

        assert handler.level == logging.WARNING

    def test_remove_handler(self, clean_logger):
        """Тест удаления обработчика"""
        handler = add_handler('stdout')
        assert handler in app_logger.handlers

        remove_handler(handler)
        assert handler not in app_logger.handlers

    def test_invalid_handler_type(self, clean_logger):
        """Тест обработки неверного типа обработчика"""
        with pytest.raises(ValueError):
            add_handler('invalid_type')

    def test_setup_with_none_handlers(self, clean_logger):
        """Тест настройки с None в качестве списка обработчиков"""
        setup_logging(handlers=None)

        assert len(app_logger.handlers) == 1
        assert isinstance(app_logger.handlers[0], logging.StreamHandler)

    def test_setup_with_invalid_handler_spec(self, clean_logger):
        """Тест обработки неверного формата спецификации обработчика"""
        with pytest.raises(ValueError):
            setup_logging(handlers=[42])

        # Тесты функции setup_logging


class TestSetupLogging:
    def test_setup_default(self, clean_logger):
        """Тест настройки с параметрами по умолчанию"""
        setup_logging()

        assert len(app_logger.handlers) == 1
        assert isinstance(app_logger.handlers[0], logging.StreamHandler)
        assert app_logger.level == logging.DEBUG

    def test_setup_custom_level(self, clean_logger):
        """Тест настройки с кастомным уровнем логирования"""
        setup_logging(level=logging.WARNING)

        assert app_logger.level == logging.WARNING

    def test_setup_multiple_handlers(self, clean_logger, temp_log_file):
        """Тест настройки с несколькими обработчиками"""
        setup_logging(handlers=['stdout', {'type': 'file', 'filename': temp_log_file}])

        assert len(app_logger.handlers) == 2
        handler_types = [type(h) for h in app_logger.handlers]
        assert logging.StreamHandler in handler_types
        assert logging.FileHandler in handler_types

    def test_setup_clears_previous_handlers(self, clean_logger):
        """Тест очистки предыдущих обработчиков"""
        # Добавляем обработчик
        add_handler('stdout')
        assert len(app_logger.handlers) == 1

        # Настраиваем логирование заново
        setup_logging()

        # Должен быть только один обработчик, а не два
        assert len(app_logger.handlers) == 1


# Тесты функциональности логирования
class TestLoggingFunctionality:
    def test_logging_to_file(self, clean_logger, temp_log_file):
        """Тест записи логов в файл"""
        setup_logging(handlers=[{'type': 'file', 'filename': temp_log_file, 'level': logging.INFO}])

        test_message = "Test log message"
        app_logger.info(test_message)

        # Проверяем, что сообщение записалось в файл
        with open(temp_log_file) as f:
            log_content = f.read()

        assert test_message in log_content

    def test_logging_levels(self, clean_logger, caplog):
        """Тест фильтрации сообщений по уровням"""
        # Настраиваем логирование с уровнем WARNING
        setup_logging(level=logging.WARNING)

        # Отправляем сообщения разных уровней
        app_logger.debug("Debug message")
        app_logger.info("Info message")
        app_logger.warning("Warning message")
        app_logger.error("Error message")

        # В логах должны быть только WARNING и ERROR
        for record in caplog.records:
            assert record.levelno >= logging.WARNING

        # Проверяем, что нужные сообщения есть в логах
        assert "Warning message" in caplog.text
        assert "Error message" in caplog.text

        # Проверяем, что ненужных сообщений нет в логах
        assert "Debug message" not in caplog.text
        assert "Info message" not in caplog.text

    def test_actual_logging(self, clean_logger, caplog):
        """Тест использования логгера с разными уровнями"""
        setup_logging(level=logging.DEBUG)

        # Логируем сообщения разных уровней
        app_logger.debug("Это отладочное сообщение")
        app_logger.info("Это информационное сообщение")
        app_logger.warning("Это предупреждение")
        app_logger.error("Это сообщение об ошибке")
        app_logger.critical("Это критическое сообщение")

        # Проверяем количество сообщений
        assert len(caplog.records) == 5

        # Проверяем уровни сообщений
        levels = [record.levelno for record in caplog.records]
        assert logging.DEBUG in levels
        assert logging.INFO in levels
        assert logging.WARNING in levels
        assert logging.ERROR in levels
        assert logging.CRITICAL in levels

    def test_rotating_file_logging(self, clean_logger, temp_log_file):
        """Тест ротации файлов журнала"""
        # Установка маленького лимита размера для быстрой ротации
        max_bytes = 100
        setup_logging(handlers=[{'type': 'rotating_file', 'filename': temp_log_file, 'maxBytes': max_bytes, 'backupCount': 3}])

        # Запись данных, превышающих лимит
        for i in range(20):
            app_logger.info(f"Сообщение номер {i} с достаточно длинным текстом для превышения лимита")

        # Проверка, что созданы ротированные файлы
        assert os.path.exists(temp_log_file)
        backup_files = [f"{temp_log_file}.1", f"{temp_log_file}.2", f"{temp_log_file}.3"]

        # Должен быть хотя бы один файл резервной копии
        assert any(os.path.exists(f) for f in backup_files)

        # Удаление созданных резервных копий
        for f in backup_files:
            if os.path.exists(f):
                os.remove(f)