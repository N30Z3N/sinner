import os
import threading
from pathlib import Path
from typing import List, Optional, ClassVar, Self

from sinner.handlers.writers.BaseImageWriter import BaseImageWriter
from sinner.helpers.FrameHelper import read_from_image
from sinner.models.NumberedFrame import NumberedFrame
from sinner.models.framebuffer.FrameBufferInterface import FrameBufferInterface
from sinner.utilities import is_absolute_path, path_exists, get_file_name, normalize_path


class FrameDirectoryBuffer(FrameBufferInterface):
    endpoint_name: ClassVar[str] = 'preview'
    _temp_dir: str

    _source_name: Optional[str] = None
    _target_name: Optional[str] = None
    _frames_count: int = 0
    _zfill_length: Optional[int] = None
    _path: Optional[str] = None
    _indices: List[int] = []
    _indices_lock: threading.RLock
    _writer: BaseImageWriter

    _loaded: bool = False  # flag to check if source & target names are loaded

    def __init__(self, temp_dir: str, writer: Optional[BaseImageWriter] = None):
        self.temp_dir = temp_dir
        self._writer = writer if writer else BaseImageWriter.create()
        self._indices_lock = threading.RLock()  # RLock позволяет повторно получать блокировку тем же потоком

    def load(self, source_name: str, target_name: str, frames_count: int) -> Self:
        self._path = None
        self._zfill_length = None
        self._source_name = source_name
        self._target_name = target_name
        self._frames_count = frames_count
        self.init_indices()
        self._loaded = True
        return self

    def flush(self) -> None:
        with self._indices_lock:
            self._path = None
            self._zfill_length = None
            self._source_name = None
            self._target_name = None
            self._frames_count = 0
            self._indices = []
            self._loaded = False

    @property
    def temp_dir(self) -> str:
        return self._temp_dir

    @temp_dir.setter
    def temp_dir(self, value: str | None) -> None:
        if not is_absolute_path(value or ''):
            raise Exception("Relative paths are not supported")
        self._temp_dir = os.path.abspath(os.path.join(str(normalize_path(value or '')), self.endpoint_name))

    @property
    def zfill_length(self) -> int:
        if self._zfill_length is None:
            self._zfill_length = len(str(self._frames_count))
        return self._zfill_length

    @staticmethod
    def make_path(path: str) -> str:
        if not path_exists(path):
            Path(path).mkdir(parents=True, exist_ok=True)
        return path

    @property
    def path(self) -> str:
        if self._path is None:
            sub_path = (os.path.basename(self._target_name or ''), os.path.basename(self._source_name or ''))
            self._path = os.path.abspath(os.path.join(self.temp_dir, *sub_path))
            self.make_path(self._path)
        return self._path

    #  Returns a processed file name for an unprocessed frame index
    def get_frame_processed_name(self, frame: NumberedFrame) -> str:
        if frame.name:
            filename = frame.name + self._writer.extension
        else:
            filename = str(frame.index).zfill(self.zfill_length) + self._writer.extension
        return str(os.path.join(self.path, filename))

    def clean(self) -> None:
        pass
        # shutil.rmtree(self._path)

    def add_frame(self, frame: NumberedFrame) -> None:
        with self._indices_lock:
            if not self._loaded:
                return
                # raise Exception(f"{self.__class__.__name__} isn't in loaded state. Call load() method properly first!")

            if not self._writer.write(frame.frame, self.get_frame_processed_name(frame)):
                raise Exception(f"Error saving frame: {self.get_frame_processed_name(frame)}")
            self._indices.append(frame.index)

    def get_frame(self, index: int, return_previous: bool = True) -> Optional[NumberedFrame]:
        if not self._loaded:  # not loaded
            return None
        if self.has_index(index):
            filename = str(index).zfill(self.zfill_length) + self._writer.extension
            filepath = str(os.path.join(self.path, filename))
            try:
                self._miss = 0
                return NumberedFrame(index, read_from_image(filepath))
            except Exception:
                pass  # Файл может быть заблокирован или поврежден
        elif return_previous:
            for previous_number in range(index - 1, 0, -1):
                if self.has_index(previous_number):
                    previous_filename = str(previous_number).zfill(self.zfill_length) + self._writer.extension
                    previous_file_path = os.path.join(self.path, previous_filename)
                    if path_exists(previous_file_path):
                        try:
                            self._miss = index - previous_number
                            return NumberedFrame(previous_number, read_from_image(previous_file_path))
                        except Exception:  # the file may exist but can be locked in another thread.
                            pass
        return None

    def has_index(self, index: int) -> bool:
        with self._indices_lock:
            return index in self._indices

    def init_indices(self) -> None:
        with self._indices_lock:
            self._indices = []
            with os.scandir(self.path) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.endswith(self._writer.extension):
                        self._indices.append(int(get_file_name(entry.name)))

    def get_indices(self) -> List[int]:
        with self._indices_lock:
            return self._indices.copy()  # prevents change of internal list from outside

    def add_index(self, index: int) -> None:
        """Adds index internally. Introduced for remote processing"""
        with self._indices_lock:
            self._indices.append(index)
