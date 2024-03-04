from sinner.handlers.frame.BaseFrameHandler import BaseFrameHandler
from sinner.helpers.FrameHelper import EmptyFrame
from sinner.models.NumberedFrame import NumberedFrame


# Empty handler for empty targets
class NoneHandler(BaseFrameHandler):

    @property
    def fps(self) -> float:
        return 0

    @property
    def fc(self) -> int:
        return 0

    @property
    def resolution(self) -> tuple[int, int]:
        return 0, 0

    def extract_frame(self, frame_number: int) -> NumberedFrame:
        return NumberedFrame(0, EmptyFrame)

    def result(self, from_dir: str, filename: str, audio_target: str | None = None) -> bool:
        return False
