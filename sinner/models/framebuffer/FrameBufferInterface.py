from typing import Self, Optional, List

from sinner.models.NumberedFrame import NumberedFrame


class FrameBufferInterface:
    _miss: int = 0  # the current miss between requested frame and the returned one

    def load(self, source_name: str, target_name: str, frames_count: int) -> Self:
        pass

    def flush(self) -> None:
        pass

    def add_frame(self, frame: NumberedFrame) -> None:
        pass

    def add_index(self, index: int) -> None:
        pass

    def get_frame(self, index: int, return_previous: bool = True) -> Optional[NumberedFrame]:
        pass

    def has_index(self, index: int) -> bool:
        pass

    def get_indices(self) -> List[int]:
        pass

    @property
    def miss(self) -> int:
        return self._miss
