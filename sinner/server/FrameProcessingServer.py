import os
import threading
import time
from argparse import Namespace
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Dict, List, Optional

from sinner.AppLogger import app_logger
from sinner.BatchProcessingCore import BatchProcessingCore
from sinner.handlers.writers.BaseImageWriter import BaseImageWriter
from sinner.server.api.messages.NotificationMessage import NotificationMessage

from sinner.server.api.messages.RequestMessage import RequestMessage
from sinner.server.api.messages.ResponseMessage import ResponseMessage
from sinner.server.api.ZMQServerAPI import ZMQServerAPI
from sinner.handlers.frame.BaseFrameHandler import BaseFrameHandler
from sinner.handlers.frame.DirectoryHandler import DirectoryHandler
from sinner.handlers.frame.EOutOfRange import EOutOfRange
from sinner.handlers.frame.NoneHandler import NoneHandler
from sinner.helpers.FrameHelper import scale
from sinner.models.Event import Event
from sinner.models.FrameTimeLine import FrameTimeLine
from sinner.models.MovingAverage import MovingAverage
from sinner.models.PerfCounter import PerfCounter
from sinner.models.State import State
from sinner.processors.frame.BaseFrameProcessor import BaseFrameProcessor
from sinner.processors.frame.FrameExtractor import FrameExtractor
from sinner.utilities import suggest_execution_threads, suggest_temp_dir
from sinner.validators.AttributeLoader import Rules, AttributeLoader


class FrameProcessingServer(AttributeLoader):
    """Server component for processing frames in a separate process."""

    # configuration variables
    frame_processor: List[str]
    temp_dir: str
    execution_threads: int
    bootstrap_processors: bool
    _prepare_frames: bool  # True: always extract and use, False: never extract nor use, Null: newer extract, use if exists. Note: attribute can't be typed as Optional[bool] due to AttributeLoader limitations
    _detailed_metrics: bool
    _scale_quality: int  # the processed frame size scale in percent
    _buffer_size: int  # Memory used for frame buffer, bytes
    _reply_endpoint: str
    _pub_endpoint: str

    # internal objects
    TimeLine: FrameTimeLine
    _processors: Dict[str, BaseFrameProcessor]
    _target_handler: Optional[BaseFrameHandler] = None
    _biggest_processed_frame: int = 0  # the last (by number) processed frame index, needed to indicate if processing gap is too big
    _average_processing_time: MovingAverage = MovingAverage(window_size=10)  # Calculator for the average processing time
    _average_frame_skip: MovingAverage = MovingAverage(window_size=10)  # Calculator for the average frame skip

    # processing state
    _source_path: str
    _target_path: str
    _position: int = 0  # player frame position

    # metrics
    _processing_fps: float = 1.0

    # threading
    _process_frames_thread: Optional[threading.Thread] = None

    # threads control events
    _event_processing: Event  # the flag to control start/stop processing thread
    _event_rewind: Event  # the flag to control if playback was rewound

    _APIHandler: ZMQServerAPI  # for now

    def rules(self) -> Rules:
        return [
            {
                'parameter': {'frame-processor', 'processor', 'processors'},
                'attribute': 'frame_processor',
                'default': ['FaceSwapper'],
                'required': True,
                'help': 'The set of frame processors to handle the target'
            },
            {
                'parameter': 'execution-threads',
                'default': suggest_execution_threads(),
                'help': 'The count of simultaneous processing threads'
            },
            {
                'parameter': {'source', 'source-path'},
                'attribute': '_source_path'
            },
            {
                'parameter': {'target', 'target-path'},
                'attribute': '_target_path'
            },
            {
                'parameter': {'quality', 'scale-quality'},
                'attribute': '_scale_quality',
                'default': 100,
                'help': 'Initial processing scale quality (in percents)'
            },
            {
                'parameter': {'prepare-frames'},
                'attribute': '_prepare_frames',
                'default': None,
                'help': 'Extract target frames to files to make realtime player run smoother'
            },
            {
                'parameter': ['bootstrap_processors', 'bootstrap'],
                'attribute': 'bootstrap_processors',
                'default': True,
                'help': 'Bootstrap frame processors on startup'
            },
            {
                'parameter': 'temp-dir',
                'default': lambda: suggest_temp_dir(self.temp_dir),
                'help': 'Select the directory for temporary files'
            },
            {
                'parameter': 'detailed-metrics',
                'attribute': '_detailed_metrics',
                'default': False,
                'help': 'Enable detailed frame processing metrics'
            },
            {
                'parameter': ['memory-buffer-size', 'memory-buffer', 'buffer-size'],
                'attribute': '_buffer_size',
                'default': 0,
                'help': 'Set memory buffer size for processed frames (in bytes)'
            },
            {
                'parameter': ['endpoint', 'reply-endpoint'],
                'attribute': '_reply_endpoint',
                'default': "tcp://127.0.0.1:5555",
                'help': 'Endpoint for the frame processor server'
            },
            {
                'parameter': ['pub-endpoint'],
                'attribute': '_pub_endpoint',
                'default': "tcp://127.0.0.1:5556",
                'help': 'Endpoint for the frame processor server publishing notifications'
            },
            {
                'module_help': 'The server for frame processing'
            }
        ]

    def __init__(self, parameters: Namespace):
        """
        Initialize the frame processor server.

        Parameters:
        parameters (Namespace): Application parameters
        endpoint (str, optional): ZeroMQ endpoint override for communication
        """
        # Initialize attribute loader first
        AttributeLoader.__init__(self, parameters)

        self._APIHandler = ZMQServerAPI(
            handler=self._handle_request,
            reply_endpoint=self._reply_endpoint,
            publish_endpoint=self._pub_endpoint
        )

        self.parameters = parameters
        self._processors = {}

        # Initialize processors if bootstrap is enabled
        if self.bootstrap_processors:
            self._processors = self.processors

        self.TimeLine = FrameTimeLine(
            temp_dir=self.temp_dir,
            buffer_size=self._buffer_size,
            writer=BaseImageWriter.create(self.frame_handler.format, self.frame_handler.quality)
        )
        self._event_processing = Event()
        self._event_rewind = Event()

    @property
    def processors(self) -> Dict[str, BaseFrameProcessor]:
        """Get or initialize frame processors."""
        try:
            for processor_name in self.frame_processor:
                if processor_name not in self._processors:
                    self._processors[processor_name] = BaseFrameProcessor.create(processor_name, self.parameters)
        except Exception as exception:  # skip, if parameters is not enough for processor
            app_logger.exception(exception)
            pass
        return self._processors

    @property
    def frame_handler(self) -> BaseFrameHandler:
        if self._target_handler is None:
            if self._target_path is None:
                self._target_handler = NoneHandler('', self.parameters)
            else:
                self._target_handler = BatchProcessingCore.suggest_handler(self._target_path, self.parameters)
        return self._target_handler

    def _handle_request(self, request: RequestMessage) -> ResponseMessage:
        """Handle client request and return response."""
        match request.type:
            case request.GET_STATUS:
                return ResponseMessage.ok_response(message="Alive")
            case request.SET_SOURCE:
                self.source_path = request.source_path
                return ResponseMessage.ok_response(message="Source path set")
            case request.GET_SOURCE:
                return ResponseMessage.ok_response(source_path=self.source_path)
            case request.SET_TARGET:
                self.target_path = request.target_path
                return ResponseMessage.ok_response(message="Target path set")
            case request.GET_TARGET:
                return ResponseMessage.ok_response(source_path=self.target_path)
            case request.SET_QUALITY:
                self.quality = request.quality
                return ResponseMessage.ok_response(message="Quality set")
            case request.GET_QUALITY:
                return ResponseMessage.ok_response(message="Quality", quality=self.quality)
            case request.SET_POSITION:
                self.rewind(request.position)
                return ResponseMessage.ok_response(message="Position set")
            case request.CMD_START_PROCESSING:
                self.start(request.position)
                return ResponseMessage.ok_response(message="Started")
            case request.CMD_STOP_PROCESSING:
                self.stop()
                return ResponseMessage.ok_response(message="Stopped")
            case request.CMD_FRAME_PROCESSED:  # process a frame immediately
                self._process_frame(request.position)
                return ResponseMessage.ok_response(message="Processed")
            case request.GET_METADATA:  # return the target metadata
                return ResponseMessage.ok_response(
                    type=ResponseMessage.METADATA,
                    render_resolution=(int(self.frame_handler.resolution[0] * self._scale_quality / 100), int(self.frame_handler.resolution[1] * self._scale_quality / 100)),
                    resolution=self.frame_handler.resolution,
                    fps=self.frame_handler.fps,
                    frames_count=self.frame_handler.fc,
                    image_format=self.frame_handler.format,
                    image_quality=self.frame_handler.quality
                )
            case request.GET_PREPARE_FRAMES:
                return ResponseMessage.ok_response(message="Prepare frames", value=self._prepare_frames)
            case request.SET_PREPARE_FRAMES:
                self.parameters.prepare_frames = request.value
                self._prepare_frames = request.value
                self.extract_frames()
                return ResponseMessage.ok_response(message="Set")
            case request.GET_FRAME:
                frame = self.frame_handler.extract_frame(request.position)
                return ResponseMessage.ok_response(
                    type=ResponseMessage.FRAME,
                    shape=frame.frame.shape,
                ).set_payload(frame.frame.tobytes())
            case request.SET_SOURCE_FILE:  # todo: unimplemented on client
                payload = request.payload()
                if payload is None:
                    return ResponseMessage.error_response(message="Empty payload")
                filename = os.path.join(self.temp_dir, "incoming", "source", request.filename)
                with open(filename, "wb") as f:
                    f.write(payload)
                self.source_path = filename
                return ResponseMessage.ok_response(message="Source file set", filename=self.source_path)
            case request.SET_TARGET_FILE:  # todo: unimplemented on client
                payload = request.payload()
                if payload is None:
                    return ResponseMessage.error_response(message="Empty payload")
                filename = os.path.join(self.temp_dir, "incoming", "target", request.filename)
                with open(filename, "wb") as f:
                    f.write(payload)
                self.target_path = filename
                return ResponseMessage.ok_response(message="Target file set", filename=self.source_path)
            case _:
                return ResponseMessage.error_response(message=f"Not implemented: {request.type}")

    def reload_parameters(self) -> None:
        self._target_handler = None
        AttributeLoader.__init__(self, self.parameters)
        for _, processor in self.processors.items():
            processor.load(self.parameters)
        self.extract_frames()

    @property
    def source_path(self) -> Optional[str]:
        return self._source_path

    @source_path.setter
    def source_path(self, value: Optional[str]) -> None:
        self.parameters.source = value
        self.reload_parameters()
        self.TimeLine.load(source_name=self._source_path, target_name=self._target_path, frame_time=self.frame_handler.frame_time, start_frame=self.TimeLine.last_requested_index, end_frame=self.frame_handler.fc)

    @property
    def target_path(self) -> Optional[str]:
        return self._target_path

    @target_path.setter
    def target_path(self, value: Optional[str]) -> None:
        self.parameters.target = value
        self.reload_parameters()
        self.TimeLine.load(source_name=self._source_path, target_name=self._target_path, frame_time=self.frame_handler.frame_time, start_frame=1, end_frame=self.frame_handler.fc)

    @property
    def quality(self) -> int:
        return self._scale_quality

    @quality.setter
    def quality(self, value: int) -> None:
        self._scale_quality = value

    def rewind(self, frame_position: int) -> None:
        if self._event_processing.is_set():
            self.TimeLine.rewind(frame_position - 1)
            self._event_rewind.set(tag=frame_position - 1)
        else:
            self._process_frame(frame_position)
        self._position = frame_position

    def start(self, start_frame: int) -> None:
        if not self._event_processing.is_set():
            self.TimeLine.reload(frame_time=self.frame_handler.frame_time, start_frame=start_frame - 1, end_frame=self.frame_handler.fc)
            self.extract_frames()
            self._start_processing(start_frame)  # run the main rendering process

    def stop(self, wait: bool = False) -> None:
        if self._event_processing.is_set():
            self._stop_processing()
            if self.TimeLine:
                self.TimeLine.stop()
            if wait:
                time.sleep(1)  # Allow time for the thread to respond

    async def start_server(self) -> None:
        await self._APIHandler.start()

    def stop_server(self) -> None:
        self._APIHandler.stop()
        self.stop(True)

    def _process_frame(self, frame_index: int) -> Optional[tuple[float, int]]:
        """
        Renders a frame with the current processors set
        :param frame_index: the frame index
        :return: the [render time, frame index], or None on error
        """
        with PerfCounter(name=f"Frame {frame_index}", collect_stats=self._detailed_metrics) as total_perf:
            try:
                # Извлечение кадра
                with total_perf.segment("extract") as _:
                    n_frame = self.frame_handler.extract_frame(frame_index)
            except EOutOfRange:
                app_logger.info(f"There's no frame {frame_index}")
                return None

            # Масштабирование
            with total_perf.segment("scale") as _:
                n_frame.frame = scale(n_frame.frame, self._scale_quality / 100)

            # Общий сегмент обработки
            with total_perf.segment("process") as _:
                # Для каждого процессора измеряем время отдельно
                for processor_name, processor in self.processors.items():
                    processor_start = time.perf_counter() if not total_perf.ns_mode else time.perf_counter_ns()
                    n_frame.frame = processor.process_frame(n_frame.frame)
                    processor_end = time.perf_counter() if not total_perf.ns_mode else time.perf_counter_ns()
                    processor_time = processor_end - processor_start

                    # Вручную записываем подсегмент
                    total_perf.record_subsegment("process", processor_name, processor_time)

            # Добавление в timeline
            with total_perf.segment("timeline") as _:
                self.TimeLine.add_frame(n_frame)

        # Вывод метрик только если активированы
        if self._detailed_metrics:
            print(total_perf)

        return total_perf.execution_time, n_frame.index

    @property
    def is_processors_loaded(self) -> bool:
        return self._processors != {}

    def extract_frames(self) -> None:
        if self._prepare_frames:
            frame_extractor = FrameExtractor(self.parameters)
            state = State(parameters=self.parameters, target_path=self._target_path, temp_dir=self.temp_dir, frames_count=self.frame_handler.fc, processor_name=frame_extractor.__class__.__name__)
            frame_extractor.configure_state(state)

            if state.is_finished:
                app_logger.info(f'Extracting frames already done ({state.processed_frames_count}/{state.frames_count})')
            else:
                if state.is_started:
                    app_logger.info(f'Temp resources for this target already exists with {state.processed_frames_count} frames extracted, continue with {state.processor_name}')
                frame_extractor.process(self.frame_handler, state)  # todo: return the GUI progressbar
                frame_extractor.release_resources()

            if state.is_finished:
                self._target_handler = DirectoryHandler(state.path, self.parameters, self.frame_handler.fps, self.frame_handler.fc, self.frame_handler.resolution)

    def _start_processing(self, start_frame: int) -> None:
        """
        Runs the main processing thread
        :param start_frame:
        """
        if not self._event_processing.is_set():
            self._event_processing.set()
            self._process_frames_thread = threading.Thread(target=self._process_frames, name="_process_frames", kwargs={
                'next_frame': start_frame,
                'end_frame': self.frame_handler.fc
            })
            self._process_frames_thread.daemon = True
            self._process_frames_thread.start()

    def _stop_processing(self) -> None:
        if self._event_processing.is_set() and self._process_frames_thread:
            self._event_processing.clear()
            self._process_frames_thread.join(1)
            self._process_frames_thread = None

    def _process_frames(self, next_frame: int, end_frame: int) -> None:
        """
        renders all frames between start_frame and end_frame
        :param next_frame:
        :param end_frame:
        """

        def process_done(future_: Future[Optional[tuple[float, int]]]) -> None:
            if not future_.cancelled():
                result = future_.result()
                if result:
                    process_time, frame_index = result
                    self._average_processing_time.update(process_time / self.execution_threads)
                    processing.remove(frame_index)
                    self._processing_fps = 1 / self._average_processing_time.get_average()
                    if self._biggest_processed_frame < frame_index:
                        self._biggest_processed_frame = frame_index

                    # Отправляем уведомление о завершении обработки
                    self._APIHandler.notify(NotificationMessage(type_=NotificationMessage.NTF_FRAME, index=frame_index, time=process_time, fps=self._processing_fps))
            futures.remove(future_)

        processing: List[int] = []  # list of frames currently being processed
        futures: list[Future[Optional[tuple[float, int]]]] = []
        processing_delta: int = 0  # additional lookahead to adjust frames synchronization

        with ThreadPoolExecutor(max_workers=self.execution_threads) as executor:  # this adds processing operations into a queue
            while next_frame <= end_frame:
                if self._event_rewind.is_set():
                    next_frame = self._event_rewind.tag or 0
                    self._event_rewind.clear()

                if next_frame not in processing and not self.TimeLine.has_index(next_frame):
                    processing.append(next_frame)
                    future: Future[Optional[tuple[float, int]]] = executor.submit(self._process_frame, next_frame)
                    future.add_done_callback(process_done)
                    futures.append(future)
                    if len(futures) >= self.execution_threads:
                        futures[:1][0].result()

                if not self._event_processing.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                self._average_frame_skip.update(self.frame_handler.fps / self._processing_fps)

                if self.TimeLine.last_added_index > self.TimeLine.last_requested_index + self.TimeLine.current_frame_miss and processing_delta > self._average_frame_skip.get_average():
                    processing_delta -= 1
                elif self.TimeLine.last_added_index < self.TimeLine.last_requested_index:
                    processing_delta += 1
                step = int(self._average_frame_skip.get_average()) + processing_delta
                if step < 1:  # preventing going backwards
                    step = 1
                next_frame += step
                # self.status.debug(msg=f"NEXT: {next_frame}, STEP: {step}, DELTA: {processing_delta}, LAST: {self.TimeLine.last_added_index}, AVG: {self._average_frame_skip.get_average()} ")
