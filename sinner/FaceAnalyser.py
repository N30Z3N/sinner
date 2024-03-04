import contextlib
import io
import threading
from typing import List
from insightface.app import FaceAnalysis
from insightface.app.common import Face

from sinner.typing import Frame


class FaceAnalyser:
    _face_analyser: FaceAnalysis | None = None
    _execution_providers: List[str]
    _less_output: bool = True

    def __init__(self, execution_providers: List[str], less_output: bool = True):
        self._execution_providers = execution_providers
        self._less_output = less_output

    @property
    def face_analyser(self) -> FaceAnalysis:
        if self._face_analyser is None:
            with threading.Lock():
                if self._less_output:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self._face_analyser = FaceAnalysis(name='buffalo_l', providers=self._execution_providers)
                        self._face_analyser.prepare(ctx_id=0, det_size=(640, 640))
                else:
                    self._face_analyser = FaceAnalysis(name='buffalo_l', providers=self._execution_providers)
                    self._face_analyser.prepare(ctx_id=0, det_size=(640, 640))
        return self._face_analyser

    def get_one_face(self, frame: Frame) -> None | Face:
        face = self.face_analyser.get(frame)
        try:
            return min(face, key=lambda x: x.bbox[0])
        except ValueError:
            return None

    def get_many_faces(self, frame: Frame) -> None | List[Face]:
        try:
            return self.face_analyser.get(frame)
        except IndexError:
            return None
