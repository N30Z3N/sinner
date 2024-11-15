from typing import Any

import numpy
from insightface.model_zoo.inswapper import INSwapper

FaceSwapperType = INSwapper
Frame = numpy.ndarray[Any, Any]
NumeratedFramePath = tuple[int, str]  # the enumerated path to a frame -> index of the frame and a path to the frame

UTF8 = "utf-8"
