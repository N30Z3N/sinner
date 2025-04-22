import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Self

import psutil

from sinner.AppLogger import app_logger
from sinner.helpers.FrameHelper import write_to_image
from sinner.models.NumberedFrame import NumberedFrame
from sinner.models.framebuffer.FrameDirectoryBuffer import FrameDirectoryBuffer


class FrameMemoryBuffer(FrameDirectoryBuffer):
    """
    A frame buffer that stores frames in memory and asynchronously saves them to disk.
    Provides the same API as FrameDirectoryBuffer with improved performance through in-memory caching.
    """

    def __init__(self, temp_dir: str, buffer_size_bytes: int = 128 * 1024 * 1024):  # Default 128MB
        super().__init__(temp_dir)
        self._buffer_size_bytes = buffer_size_bytes
        self._memory_buffer: Dict[int, NumberedFrame] = {}
        self._buffer_lock = threading.RLock()
        self._buffer_condition = threading.Condition(self._buffer_lock)
        self._current_buffer_size_bytes = 0
        self._frame_sizes: Dict[int, int] = {}
        self._disk_write_executor = ThreadPoolExecutor(max_workers=psutil.cpu_count())
        # Словарь для отслеживания статуса записи кадров на диск
        self._disk_write_status: Dict[int, bool] = {}
        self._disk_write_status_lock = threading.RLock()

    def load(self, source_name: str, target_name: str, frames_count: int) -> Self:
        """Load source/target pair to the buffer."""
        with self._buffer_lock:
            # Clear memory buffer before loading new data
            self._memory_buffer.clear()
            self._frame_sizes.clear()
            self._current_buffer_size_bytes = 0

        with self._disk_write_status_lock:
            self._disk_write_status.clear()

        return super().load(source_name, target_name, frames_count)

    def add_frame(self, frame: NumberedFrame) -> None:
        """
        Add a frame to the buffer. Stores frame in memory and asynchronously writes to disk.
        Blocks if the buffer is full until space becomes available.
        """
        # Calculate frame size in bytes
        frame_size = frame.frame.nbytes

        app_logger.debug(f"Adding frame {frame.index} to buffer (size: {frame_size} bytes)")

        with self._buffer_lock:
            # If buffer is already full, wait until space is available
            while self._current_buffer_size_bytes + frame_size > self._buffer_size_bytes:
                app_logger.debug(f"Memory buffer full ({self._current_buffer_size_bytes}/{self._buffer_size_bytes} bytes), waiting for space")
                self._buffer_condition.wait()

            # Add frame to memory buffer
            self._memory_buffer[frame.index] = frame
            self._frame_sizes[frame.index] = frame_size
            self._current_buffer_size_bytes += frame_size
            app_logger.debug(f"Frame {frame.index} added to memory buffer (buffer size: {self._current_buffer_size_bytes} bytes)")

            # Add to indices
            with self._indices_lock:
                if not self._loaded:
                    app_logger.warning("Buffer not loaded, frame index not added")
                    return
                if frame.index not in self._indices:
                    self._indices.append(frame.index)
                    app_logger.debug(f"Added frame {frame.index} to indices list")

        # Отмечаем, что запись на диск еще не завершена
        with self._disk_write_status_lock:
            self._disk_write_status[frame.index] = False

        # Асинхронно сохраняем на диск
        self._disk_write_executor.submit(self._save_frame_to_disk, frame)

    def _save_frame_to_disk(self, frame: NumberedFrame) -> None:
        """Save frame to disk asynchronously."""
        start_time = time.time()
        try:
            frame_path = self.get_frame_processed_name(frame)
            app_logger.debug(f"Writing frame {frame.index} to disk at {frame_path}")

            if not write_to_image(frame.frame, frame_path):
                app_logger.error(f"Failed to save frame {frame.index} to disk: {frame_path}")
                return

            app_logger.debug(f"Successfully wrote frame {frame.index} to disk in {time.time() - start_time:.4f}s")

            # Отмечаем успешное сохранение
            with self._disk_write_status_lock:
                self._disk_write_status[frame.index] = True

        except Exception as e:
            app_logger.exception(f"Error saving frame {frame.index} to disk: {e}")
            # Отмечаем ошибку сохранения
            with self._disk_write_status_lock:
                self._disk_write_status[frame.index] = False

    def get_frame(self, index: int, return_previous: bool = True) -> NumberedFrame | None:
        """
        Get a frame by index. Checks memory buffer first, then disk.
        Removes the frame from memory buffer after retrieval.
        """
        app_logger.debug(f"Requesting frame {index} (return_previous={return_previous})")

        # First check if the frame is in memory
        with self._buffer_lock:
            if index in self._memory_buffer:
                frame = self._memory_buffer.pop(index)
                frame_size = self._frame_sizes.pop(index)
                self._current_buffer_size_bytes -= frame_size
                self._miss = 0

                if frame.frame is None or frame.frame.size == 0:
                    app_logger.warning(f"Empty frame {index} retrieved from memory buffer!")
                else:
                    app_logger.debug(f"Frame {index} retrieved from memory buffer (size: {frame_size} bytes)")

                # Notify waiting threads that space is now available
                self._buffer_condition.notify_all()
                return frame

        # Если кадра нет в памяти, проверяем, был ли он записан на диск
        disk_write_status = False
        with self._disk_write_status_lock:
            disk_write_status = self._disk_write_status.get(index, False)

        if index in self._indices and not disk_write_status:
            app_logger.warning(f"Frame {index} is in indices but disk write is not complete, possible race condition")
            # Небольшая задержка, чтобы дать шанс асинхронной записи завершиться
            time.sleep(0.01)

        # If not in memory, check disk using parent implementation
        app_logger.debug(f"Frame {index} not in memory, checking disk")

        # Используем родительский метод для получения кадра с диска
        result = super().get_frame(index, return_previous)

        if result is None:
            app_logger.warning(f"Frame {index} not found in memory or on disk!")
        elif result.frame is None or result.frame.size == 0:
            app_logger.warning(f"Empty frame {result.index} retrieved from disk!")
        else:
            app_logger.debug(f"Frame {result.index} retrieved from disk")

        return result

    def has_index(self, index: int) -> bool:
        """Check if frame exists in memory or on disk."""
        # Check memory buffer first
        with self._buffer_lock:
            if index in self._memory_buffer:
                return True

        # Then check disk
        disk_result = super().has_index(index)
        app_logger.debug(f"Frame {index} {'found' if disk_result else 'not found'} on disk")
        return disk_result

    def flush(self) -> None:
        """Clear memory buffer and reset disk buffer."""
        app_logger.debug("Flushing memory and disk buffers")

        # First flush disk storage
        super().flush()

        # Then clear memory buffer
        with self._buffer_lock:
            self._memory_buffer.clear()
            self._frame_sizes.clear()
            self._current_buffer_size_bytes = 0
            app_logger.debug("Memory buffer cleared")

            # Notify any waiting threads
            self._buffer_condition.notify_all()

        with self._disk_write_status_lock:
            self._disk_write_status.clear()
            app_logger.debug("Disk write status cleared")

    def init_indices(self) -> None:
        """Initialize indices from disk and memory."""
        # Initialize indices from disk
        app_logger.debug("Initializing indices from disk and memory")
        super().init_indices()

        # Add indices from memory buffer
        with self._buffer_lock, self._indices_lock:
            memory_indices = list(self._memory_buffer.keys())
            for index in memory_indices:
                if index not in self._indices:
                    self._indices.append(index)
            app_logger.debug(f"Added {len(memory_indices)} indices from memory buffer")
            app_logger.debug(f"Total indices count: {len(self._indices)}")

    def clean(self) -> None:
        """Clean temporary files and memory buffer."""
        app_logger.debug("Cleaning temporary files and memory buffer")

        # Clean disk storage
        super().clean()

        # Clean memory buffer
        with self._buffer_lock:
            self._memory_buffer.clear()
            self._frame_sizes.clear()
            self._current_buffer_size_bytes = 0
            app_logger.debug("Memory buffer cleared during clean")

        with self._disk_write_status_lock:
            self._disk_write_status.clear()
            app_logger.debug("Disk write status cleared during clean")

    def __del__(self) -> None:
        """Clean up resources when object is deleted."""
        app_logger.debug("Cleaning up FrameMemoryBuffer resources")
        if hasattr(self, '_disk_write_executor'):
            self._disk_write_executor.shutdown(wait=False)
