import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Self, Optional, Any

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

    def __init__(self, temp_dir: str, buffer_size: int = 128 * 1024 * 1024, remove_earlier_frames: bool = False):
        """
        Initialize a memory buffer with disk storage.

        Args:
            temp_dir: Directory for temporary files
            buffer_size: Maximum memory buffer size in bytes. Set to 0 to disable memory buffer completely.
            remove_earlier_frames: If True, when a frame is requested, all frames with lower indices will be removed from memory
        """
        super().__init__(temp_dir)
        self._buffer_size: int = buffer_size
        self._memory_buffer: Dict[int, NumberedFrame] = {}
        self._buffer_lock: threading.RLock = threading.RLock()
        self._current_buffer_size: int = 0
        self._frame_sizes: Dict[int, int] = {}
        self._disk_write_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=psutil.cpu_count())
        self._remove_earlier_frames: bool = remove_earlier_frames  # Default strategy for removing earlier frames

    def load(self, source_name: str, target_name: str, frames_count: int) -> Self:
        """Load source/target pair to the buffer."""
        if self._buffer_size > 0:
            with self._buffer_lock:
                # Clear memory buffer before loading new data
                self._memory_buffer.clear()
                self._frame_sizes.clear()
                self._current_buffer_size = 0

        return super().load(source_name, target_name, frames_count)

    def add_frame(self, frame: NumberedFrame) -> None:
        """
        Add a frame to the buffer. Stores frame in memory and asynchronously writes to disk.
        If the buffer is full, writes directly to disk without storing in memory.
        """
        if self._buffer_size > 0:
            frame_size = frame.frame.nbytes  # Calculate frame size in bytes
            with self._buffer_lock:
                if self._current_buffer_size + frame_size > self._buffer_size:
                    # Буфер заполнен, сразу записываем на диск без сохранения в памяти
                    app_logger.info(f"Memory buffer full ({self._current_buffer_size}/{self._buffer_size} bytes), frame {frame.index} stored directly to disk")
                    self._save_frame_to_disk(frame)
                    return

                # Add frame to memory buffer
                self._memory_buffer[frame.index] = frame
                self._frame_sizes[frame.index] = frame_size
                self._current_buffer_size += frame_size

            self._disk_write_executor.submit(self._save_frame_to_disk, frame)  # Асинхронно сохраняем на диск
        else:
            self._save_frame_to_disk(frame)  # Если буфер отключён, то записываем синхронно

    def _save_frame_to_disk(self, frame: NumberedFrame) -> None:
        """Save frame to disk asynchronously."""
        try:
            frame_path = self.get_frame_processed_name(frame)

            if not write_to_image(frame.frame, frame_path):
                app_logger.error(f"Failed to save frame {frame.index} to disk: {frame_path}")
                return

            # Добавляем индекс в список только после успешной записи на диск
            with self._indices_lock:
                if frame.index not in self._indices:
                    self._indices.append(frame.index)

        except Exception as e:
            app_logger.exception(f"Error saving frame {frame.index} to disk: {e}")

    def get_frame(self, index: int, return_previous: bool = True, remove_earlier_frames: Optional[bool] = None) -> NumberedFrame | None:
        """
        Get a frame by index. Checks memory buffer first, then disk.
        Removes the frame from memory buffer after retrieval.

        Args:
            index: The index of the frame to retrieve
            return_previous: If True, return the previous frame if the requested frame is not found
            remove_earlier_frames: If True, also removes frames with indices lower than the requested index.
                                  If None, uses the default strategy set during initialization.
        """
        # First check if the frame is in memory
        if self._buffer_size > 0:
            # Determine which clearing strategy to use
            clear_strategy = self._remove_earlier_frames if remove_earlier_frames is None else remove_earlier_frames
            with self._buffer_lock:
                if index in self._memory_buffer:
                    # Get the requested frame
                    frame = self._memory_buffer.pop(index)
                    frame_size = self._frame_sizes.pop(index)
                    self._current_buffer_size -= frame_size

                    # If we need to remove earlier frames
                    if clear_strategy:
                        earlier_indices = [i for i in list(self._memory_buffer.keys()) if i < index]
                        if earlier_indices:
                            app_logger.debug(f"Removing {len(earlier_indices)} earlier frames (indices below {index})")

                        for earlier_index in earlier_indices:
                            earlier_frame_size = self._frame_sizes.pop(earlier_index)
                            self._memory_buffer.pop(earlier_index)
                            self._current_buffer_size -= earlier_frame_size

                    self._miss = 0
                    return frame

        # Используем родительский метод для получения кадра с диска
        result = super().get_frame(index, return_previous)

        if result is None:
            app_logger.warning(f"Frame {index} not found in memory or on disk!")
        elif result.frame is None or result.frame.size == 0:
            app_logger.warning(f"Empty frame {result.index} retrieved from disk!")

        return result

    def has_index(self, index: int) -> bool:
        """Check if frame exists in memory or on disk."""
        # Check memory buffer first
        with self._buffer_lock:
            if index in self._memory_buffer:
                return True

        # Then check disk
        return super().has_index(index)

    def flush(self) -> None:
        """Clear memory buffer and reset disk buffer."""

        # First flush disk storage
        super().flush()
        if self._buffer_size > 0:
            with self._buffer_lock:
                self._memory_buffer.clear()
                self._frame_sizes.clear()
                self._current_buffer_size = 0

    def init_indices(self) -> None:
        """Initialize indices from disk and memory."""
        # Initialize indices from disk
        super().init_indices()

        # Add indices from memory buffer
        with self._buffer_lock, self._indices_lock:
            memory_indices = list(self._memory_buffer.keys())
            for index in memory_indices:
                if index not in self._indices:
                    self._indices.append(index)

    def clean(self) -> None:
        """Clean temporary files and memory buffer."""

        # Clean disk storage
        super().clean()
        if self._buffer_size > 0:
            # Clean memory buffer
            with self._buffer_lock:
                self._memory_buffer.clear()
                self._frame_sizes.clear()
                self._current_buffer_size = 0

    def get_buffer_info(self) -> Dict[str, Any]:
        """
        Get information about the current state of the memory buffer.

        Returns:
            A dictionary with buffer statistics
        """
        with self._buffer_lock:
            return {
                "frames_in_memory": len(self._memory_buffer),
                "memory_usage_bytes": self._current_buffer_size,
                "memory_limit_bytes": self._buffer_size,
                "usage_percent": (self._current_buffer_size / self._buffer_size) * 100 if self._buffer_size > 0 else 0,
                "frame_indices_in_memory": sorted(list(self._memory_buffer.keys())),
                "remove_earlier_frames_strategy": self._remove_earlier_frames
            }

    def __del__(self) -> None:
        """Clean up resources when object is deleted."""
        if hasattr(self, '_disk_write_executor'):
            self._disk_write_executor.shutdown(wait=False)
