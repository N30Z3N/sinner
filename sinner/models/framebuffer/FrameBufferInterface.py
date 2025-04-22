from abc import abstractmethod
from typing import Self, Optional, List

from sinner.models.NumberedFrame import NumberedFrame


class FrameBufferInterface:
    _miss: int = 0  # the current miss between requested frame and the returned one

    @abstractmethod
    def load(self, source_name: str, target_name: str, frames_count: int) -> Self:
        pass

    @abstractmethod
    def flush(self) -> None:
        pass

    @abstractmethod
    def add_frame(self, frame: NumberedFrame) -> None:
        pass

    @abstractmethod
    def add_index(self, index: int) -> None:
        pass

    @abstractmethod
    def get_frame(self, index: int, return_previous: bool = True) -> Optional[NumberedFrame]:
        pass

    @abstractmethod
    def has_index(self, index: int) -> bool:
        pass

    @abstractmethod
    def get_indices(self) -> List[int]:
        pass

    @property
    def miss(self) -> int:
        return self._miss
