import logging
from typing import Optional, Dict

from colorama import Fore, Back, Style


class LevelBasedFormatter(logging.Formatter):
    """Форматтер с разными форматами в зависимости от уровня логирования"""

    def __init__(self, formats: Dict[Optional[int], str]):
        """
        Инициализация с разными форматами для разных уровней
        :param formats: dict с уровнями логирования в качестве ключей и строками форматирования в качестве значений
        """
        # Формат по умолчанию
        self.default_fmt = formats.get(None, '%(levelname)s - %(message)s')
        # Форматы для конкретных уровней
        self.formats = formats
        super().__init__(self.default_fmt)

    def format(self, record: logging.LogRecord) -> str:
        # Сохраняем оригинальный формат
        # noinspection PyProtectedMember
        original_fmt = self._style._fmt

        # Выбираем формат в зависимости от уровня
        if record.levelno in self.formats:
            self._style._fmt = self.formats[record.levelno]
        else:
            self._style._fmt = self.default_fmt

        # Форматируем запись
        result = super().format(record)

        # Восстанавливаем оригинальный формат
        self._style._fmt = original_fmt

        return result


class ColoredFormatter(LevelBasedFormatter):
    """Форматтер для цветного вывода в консоль с разными форматами для разных уровней"""

    def format(self, record: logging.LogRecord) -> str:
        # Форматируем сообщение с учетом разных форматов по уровням
        log_message = super().format(record)

        # Подбираем цвет в зависимости от уровня
        colors = {
            logging.DEBUG: Fore.CYAN + Back.BLACK,
            logging.INFO: Fore.LIGHTWHITE_EX + Back.BLACK,
            logging.WARNING: Fore.YELLOW + Back.BLACK,
            logging.ERROR: Fore.BLACK + Back.RED,
            logging.CRITICAL: Fore.WHITE + Back.RED
        }

        # Применяем цвет к сообщению
        color = colors.get(record.levelno, '')
        return f"{color}{log_message}{Style.RESET_ALL}"


# Создаем глобальный логгер приложения
app_logger = logging.getLogger("sinner")


def setup_logging(level: int = logging.DEBUG, log_file: Optional[str] = None) -> None:
    """Настройка логгера при запуске приложения"""
    # Очистка предыдущих обработчиков
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)

    # Настройка логгера
    app_logger.setLevel(level)

    # Определяем форматы для разных уровней
    formats = {
        # Подробный формат для отладки, ошибок и критических ошибок
        logging.DEBUG: '%(module)s.%(funcName)s:%(lineno)d: %(message)s',
        logging.ERROR: '%(module)s.%(funcName)s:%(lineno)d: %(message)s',
        logging.CRITICAL: '%(module)s.%(funcName)s:%(lineno)d: %(message)s',
        # Более компактный формат для info и warning
        logging.INFO: '%(module)s: %(message)s',
        logging.WARNING: '%(module)s: %(message)s',
        # Формат по умолчанию
        None: '%(module)s: %(message)s'
    }

    # Файловый обработчик (если указан), без цветов
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = LevelBasedFormatter(formats)
        file_handler.setFormatter(file_formatter)
        app_logger.addHandler(file_handler)
    else:
        # Консольный обработчик с цветным форматтером
        console_handler = logging.StreamHandler()
        console_formatter = ColoredFormatter(formats)
        console_handler.setFormatter(console_formatter)
        app_logger.addHandler(console_handler)
