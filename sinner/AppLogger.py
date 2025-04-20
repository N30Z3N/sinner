import logging
from logging.handlers import SysLogHandler, RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional, Dict, List, Union, Any

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

# Определяем форматы для разных уровней (глобально)
DEFAULT_FORMATS = {
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

# Типы обработчиков
HandlerType: List[str] = ['stdout', 'file', 'syslog', 'rotating_file', 'timed_rotating_file']


def add_handler(handler_type: str, level: int = logging.NOTSET, **kwargs) -> logging.Handler:  # type: ignore[no-untyped-def]
    """
    Добавляет обработчик указанного типа к глобальному логгеру
    
    :param handler_type: Тип обработчика ('stdout', 'file', 'syslog', 'rotating_file', 'timed_rotating_file')
    :param level: Уровень логирования для обработчика
    :param kwargs: Дополнительные параметры для обработчика
    :return: Созданный обработчик
    """

    if handler_type == 'stdout':
        # Получение кастомных форматов или использование стандартных
        formats = kwargs.pop('formats', DEFAULT_FORMATS)
        handler: logging.Handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter(formats))

    elif handler_type == 'file':
        filename = kwargs.pop('filename', 'sinner.log')
        formats = kwargs.pop('formats', DEFAULT_FORMATS)
        mode = kwargs.pop('mode', 'a')  # По умолчанию используем append режим
        encoding = kwargs.pop('encoding', None)

        handler = logging.FileHandler(filename, mode=mode, encoding=encoding)
        handler.setFormatter(LevelBasedFormatter(formats))

    elif handler_type == 'syslog':
        address = kwargs.pop('address', '/dev/log')
        facility = kwargs.pop('facility', SysLogHandler.LOG_USER)
        socktype = kwargs.pop('socktype', None)
        formats = kwargs.pop('formats', DEFAULT_FORMATS)

        handler = SysLogHandler(address=address, facility=facility, socktype=socktype)
        handler.setFormatter(LevelBasedFormatter(formats))

    elif handler_type == 'rotating_file':
        filename = kwargs.pop('filename', 'sinner.rotate.log')
        max_bytes = kwargs.pop('maxBytes', 10 * 1024 * 1024)  # 10MB по умолчанию
        backup_count = kwargs.pop('backupCount', 5)  # 5 файлов по умолчанию
        formats = kwargs.pop('formats', DEFAULT_FORMATS)

        handler = RotatingFileHandler(filename, maxBytes=max_bytes, backupCount=backup_count)
        handler.setFormatter(LevelBasedFormatter(formats))

    elif handler_type == 'timed_rotating_file':
        filename = kwargs.pop('filename', 'sinner.rotate.log')
        when = kwargs.pop('when', 'D')  # По умолчанию ежедневно
        interval = kwargs.pop('interval', 1)
        backup_count = kwargs.pop('backupCount', 7)  # 7 файлов по умолчанию
        formats = kwargs.pop('formats', DEFAULT_FORMATS)

        handler = TimedRotatingFileHandler(filename, when=when, interval=interval, backupCount=backup_count)
        handler.setFormatter(LevelBasedFormatter(formats))

    else:
        raise ValueError(f"Неизвестный тип обработчика: {handler_type}")

    if level != logging.NOTSET:
        handler.setLevel(level)

    app_logger.addHandler(handler)
    return handler


def remove_handler(handler: logging.Handler) -> None:
    """
    Удаляет указанный обработчик из глобального логгера

    :param handler: Обработчик для удаления
    """
    if handler in app_logger.handlers:
        app_logger.removeHandler(handler)


def setup_logging(level: int = logging.DEBUG, handlers: Optional[Union[List[str], List[Dict[str, Any]]]] = None) -> None:
    """
    Настройка логгера при запуске приложения
    
    :param level: Уровень логирования для глобального логгера
    :param handlers: Список обработчиков для настройки. 
                    Каждый элемент может быть строкой типа обработчика
                    или словарем с ключами 'type', 'level' и другими параметрами.
                    Пример: ['console', {'type': 'file', 'filename': 'app.log', 'level': logging.INFO}]
    """
    # Очистка предыдущих обработчиков
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)

    # Настройка уровня логгера
    app_logger.setLevel(level)

    # Если handlers не указаны, используем консоль по умолчанию
    if handlers is None:
        handlers = ['stdout']

    # Добавляем все указанные обработчики
    for handler_spec in handlers:
        if isinstance(handler_spec, str):
            add_handler(handler_spec)
        elif isinstance(handler_spec, dict):
            handler_type = handler_spec.pop('type')
            handler_level = handler_spec.pop('level', logging.NOTSET)
            add_handler(handler_type, handler_level, **handler_spec)
        else:
            raise ValueError(f"Неверный формат спецификации обработчика: {handler_spec}")
