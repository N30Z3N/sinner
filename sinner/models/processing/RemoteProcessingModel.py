import os
import threading
import time
from argparse import Namespace
from tkinter import IntVar
from typing import Callable, Any, Optional

from sinner.AppLogger import app_logger
from sinner.gui.controls.FramePlayer.PygameFramePlayer import PygameFramePlayer
from sinner.gui.controls.ProgressIndicator.BaseProgressIndicator import BaseProgressIndicator
from sinner.server.FrameProcessingClient import FrameProcessingClient
from sinner.server.api.messages.NotificationMessage import NotificationMessage
from sinner.server.api.ZMQClientAPI import ZMQClientAPI
from sinner.models.Event import Event
from sinner.models.FrameTimeLine import FrameTimeLine
from sinner.models.MediaMetaData import MediaMetaData
from sinner.models.audio.BaseAudioBackend import BaseAudioBackend
from sinner.models.processing.ProcessingModelInterface import ProcessingModelInterface, PROCESSED, EXTRACTED
from sinner.utilities import normalize_path, seconds_to_hmsms, list_class_descendants, resolve_relative_path, suggest_temp_dir
from sinner.validators.AttributeLoader import Rules, AttributeLoader


class RemoteProcessingModel(AttributeLoader, ProcessingModelInterface):
    """
    GUI model that uses remote processing.
    """

    # Client-server
    ProcessingClient: FrameProcessingClient  # Client side
    _reply_endpoint: str
    _sub_endpoint: str
    _timeout: int

    def rules(self) -> Rules:
        return [
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
                'parameter': ['sound', 'enable-sound'],
                'attribute': '_enable_sound',
                'default': True,
                'help': 'Enable audio playback'
            },
            {
                'parameter': ['audio-backend', 'audio'],
                'attribute': '_audio_backend',
                'default': 'VLCAudioBackend',
                'choices': list_class_descendants(resolve_relative_path('../audio'), 'BaseAudioBackend'),
                'help': 'Audio backend to use'
            },
            {
                'parameter': 'temp-dir',
                'default': lambda: suggest_temp_dir(self.temp_dir),
                'help': 'Select the directory for temporary files'
            },
            {
                'parameter': ['endpoint', 'reply-endpoint'],
                'attribute': '_reply_endpoint',
                'default': "tcp://127.0.0.1:5555",
                'help': 'Endpoint for the frame processor server'
            },
            {
                'parameter': ['sub-endpoint'],
                'attribute': '_sub_endpoint',
                'default': "tcp://127.0.0.1:5556",
                'help': 'Endpoint for the frame processor server reply notifications'
            },
            {
                'parameter': ['timeout'],
                'attribute': '_timeout',
                'default': 5000,
                'help': 'Network communications timeout'
            },
            {
                'module_help': 'Distributed GUI processing client model'
            }
        ]

    def __init__(self, parameters: Namespace, status_callback: Callable[[str, str], Any], on_close_event: Optional[Event] = None, progress_control: Optional[BaseProgressIndicator] = None):
        """
        Initialize the distributed GUI model.

        Parameters:
        parameters (Namespace): Application parameters
        status_callback (Callable): Function to call with status updates
        on_close_event (Event, optional): Event to trigger on window close
        progress_control (BaseProgressIndicator, optional): Progress indicator control
        """
        self.parameters = parameters
        super().__init__(parameters)
        self._status = status_callback
        self._status("Connection", f"Connecting to {self._reply_endpoint}")
        # Initialize processor client
        self.ProcessingClient = FrameProcessingClient(
            ZMQClientAPI(
                notification_handler=self.notification_handler,
                sub_endpoint=self._sub_endpoint,
                reply_endpoint=self._reply_endpoint,
                timeout=self._timeout
            )
        )

        if not self.ProcessingClient.connected:
            self._status("Connection", f"Timeout connecting to {self._reply_endpoint}")
        else:
            self._status("Connection", f"Connected to {self._reply_endpoint}")

        if self._source_path:
            self.ProcessingClient.source_path = self._source_path
        if self._target_path:
            self.ProcessingClient.target_path = self._target_path

        # Set up the timeline and player
        self.TimeLine = FrameTimeLine(temp_dir=self.temp_dir).load(source_name=self._source_path, target_name=self._target_path, frame_time=self.metadata.frame_time, start_frame=1, end_frame=self.metadata.frames_count)
        self.Player = PygameFramePlayer(width=self.metadata.resolution[0], height=self.metadata.resolution[1], caption='sinner distributed player', on_close_event=on_close_event)

        # Initialize audio if enabled
        if self._enable_sound:
            self.AudioPlayer = BaseAudioBackend.create(self._audio_backend, parameters=self.parameters, media_path=self._target_path)

        # Set progress control and status callback
        self.progress_control = progress_control

        self._status("Time position", seconds_to_hmsms(0))
        self._status("Frame position", f'{self.position.get()}/{self.metadata.frames_count}')

        # Initialize event flags
        self._event_playback = Event()
        app_logger.info("Distributed GUI model initialized")

    def reload_parameters(self) -> None:
        """Reload parameters and update components."""
        self.MetaData = None
        super().__init__(self.parameters)

    def enable_sound(self, enable: bool | None = None) -> bool:
        """
        Enable or disable sound playback.

        Parameters:
        enable (bool, optional): If provided, enables or disables sound

        Returns:
        bool: Current sound enabled state
        """
        if enable is not None:
            self._enable_sound = enable
            if self._enable_sound and not self.AudioPlayer:
                self.AudioPlayer = BaseAudioBackend.create(self._audio_backend, parameters=self.parameters, media_path=self._target_path)
            elif self.AudioPlayer:
                self.AudioPlayer.stop()
                self.AudioPlayer = None
        return self._enable_sound

    @property
    def audio_backend(self) -> str:
        """Get the current audio backend name."""
        return self._audio_backend

    @audio_backend.setter
    def audio_backend(self, backend: str) -> None:
        """Set the audio backend."""
        self.enable_sound(False)
        self._audio_backend = backend
        self.enable_sound(True)

    @property
    def source_path(self) -> str | None:
        """Get the current source path."""
        return self._source_path

    @source_path.setter
    def source_path(self, value: str | None) -> None:
        """Set the source path and update related components."""
        self.parameters.source = value
        self.reload_parameters()

        # Update timeline
        self.TimeLine.load(source_name=self._source_path, target_name=self._target_path, frame_time=self.metadata.frame_time, start_frame=self.TimeLine.last_requested_index, end_frame=self.metadata.frames_count)

        # Update progress control
        self.progress_control = self.ProgressBar

        # Update source in processor client
        self.ProcessingClient.source_path = self._source_path

        # Update preview if not playing
        if not self.player_is_started:
            self.update_preview()

    @property
    def target_path(self) -> str | None:
        """Get the current target path."""
        return self._target_path

    @target_path.setter
    def target_path(self, value: str | None) -> None:
        """Set the target path and update related components."""
        self.parameters.target = value
        self.reload_parameters()
        self.position.set(1)

        # Update target in processor client
        self.ProcessingClient.target_path = self.target_path

        # Clear player and reset timeline
        self.Player.clear()
        self.TimeLine.load(source_name=self._source_path, target_name=self._target_path, frame_time=self.metadata.frame_time, start_frame=1, end_frame=self.metadata.frames_count)
        # Update progress control
        self.progress_control = self.ProgressBar

        # Update audio if enabled
        if self._enable_sound:
            if self.AudioPlayer:
                self.AudioPlayer.stop()
            self.AudioPlayer = BaseAudioBackend.create(self._audio_backend, parameters=self.parameters, media_path=self._target_path)

        # Update playback state
        if self.player_is_started:
            self.player_stop()
            self.player_start(start_frame=self.position.get())
        else:
            self.update_preview()
            self._status("Time position", seconds_to_hmsms(0))
            self._status("Frame position", f'{self.position.get()}/{self.metadata.frames_count}')

    @property
    def source_dir(self) -> str | None:
        """Get the directory containing the source file."""
        return normalize_path(os.path.dirname(self._source_path)) if self._source_path else None

    @property
    def target_dir(self) -> str | None:
        """Get the directory containing the target file."""
        return normalize_path(os.path.dirname(self._target_path)) if self._target_path else None

    @property
    def quality(self) -> int:
        """Get the processing quality as a percentage (0-100)."""
        return self.ProcessingClient.quality

    @quality.setter
    def quality(self, value: int) -> None:
        """Set the processing quality from a percentage."""
        self.ProcessingClient.quality = value
        self.MetaData = None  # clear metadata to refresh scaled quality value

    @property
    def position(self) -> IntVar:
        """Get the current position variable for GUI controls."""
        if self._positionVar is None:
            self._positionVar = IntVar(value=1)
        return self._positionVar

    @property
    def volume(self) -> IntVar:
        """Get the current volume variable for GUI controls."""
        if self._volumeVar is None:
            self._volumeVar = IntVar(value=self.AudioPlayer.volume if self.AudioPlayer else 0)
        return self._volumeVar

    @property
    def metadata(self) -> MediaMetaData:
        if self.MetaData is None:
            remote_metadata = self.ProcessingClient.metadata
            if remote_metadata is None:  # isn't ready
                return MediaMetaData()
            else:
                self.MetaData = remote_metadata
        return self.MetaData

    @property
    def player_is_started(self) -> bool:
        """Check if playback is active."""
        return self._event_playback.is_set()

    def update_preview(self, processed: Optional[bool] = None) -> None:
        """
        Update the preview image.

        Parameters:
        processed (bool): If True, shows processed frame, otherwise shows original frame
        """
        if processed is None:  # prevents requesting to process without target
            processed = (self._source_path and self._target_path) is not None  # todo: проверить и отладить поведение, в случае, если у сервера нет source/target

        frame_number = self.position.get()

        if not processed:  # base frame requested
            try:
                preview_frame = self.ProcessingClient.get_frame(frame_number)
            except Exception as exception:
                app_logger.exception(exception)
                preview_frame = None
        else:
            # Check if frame is already in timeline
            if not self.TimeLine.has_index(frame_number):
                # If not, check if it's processed on the server
                if self.ProcessingClient.get_processed_frame(frame_number):
                    self.TimeLine.add_frame_index(frame_number)
                else:
                    app_logger.error(f"Error awaiting frame {frame_number} from the server")
            # Try to get the frame from timeline
            preview_frame = self.TimeLine.get_frame_by_index(frame_number)

        # Display frame if available
        if preview_frame:
            self.Player.show_frame(preview_frame.frame)
            self.set_progress_index_value(self.position.get(), PROCESSED if processed else EXTRACTED)
        else:
            self.Player.clear()

    def set_volume(self, volume: int) -> None:
        """Set audio playback volume."""
        if self.AudioPlayer:
            self.AudioPlayer.volume = volume

    def rewind(self, frame_position: int) -> None:
        """
        Change playback position to specified frame.

        Parameters:
        frame_position (int): Target frame number
        """
        if self.player_is_started:
            self.TimeLine.rewind(frame_position - 1)
        else:
            self.update_preview()

        self.position.set(frame_position)

        if self.AudioPlayer:
            self.AudioPlayer.position = int(frame_position * self.metadata.frame_time)

        self._status("Time position", seconds_to_hmsms(self.metadata.frame_time * (frame_position - 1)))
        self._status("Frame position", f'{self.position.get()}/{self.metadata.frames_count}')

        # Update server with new requested position
        self.ProcessingClient.rewind(frame_position)

    def player_start(self, start_frame: int, on_stop_callback: Optional[Callable[..., Any]] = None) -> None:
        self._on_stop_callback = on_stop_callback
        if not self.player_is_started:
            self.TimeLine.reload(frame_time=self.metadata.frame_time, start_frame=start_frame - 1, end_frame=self.metadata.frames_count)
            if self.AudioPlayer:
                self.AudioPlayer.position = int(start_frame * self.metadata.frame_time)

            # Start processing and playback threads
            self.__start_processing(start_frame)
            self.__start_playback()

            if self.AudioPlayer:
                self.AudioPlayer.play()

    def player_stop(self, wait: bool = False, shutdown: bool = False) -> None:
        """
        Stop playback.

        Parameters:
        wait (bool): If True, wait for threads to stop
        reload_frames (bool): If True, reload frames on next start
        """
        if self.player_is_started:
            if self.AudioPlayer:
                self.AudioPlayer.stop()

            self.__stop_processing()
            self.__stop_playback()

            if self.TimeLine:
                self.TimeLine.stop()

            if wait:
                time.sleep(1)  # Allow time for threads to stop

        if self._on_stop_callback:
            self._on_stop_callback()

    def __start_processing(self, start_frame: int) -> None:
        """
        Start the processing thread.

        Parameters:
        start_frame (int): Frame to start processing from
        """

        self.ProcessingClient.start(start_frame)

    def __stop_processing(self) -> None:
        """Stop the processing thread."""
        self.ProcessingClient.stop()

    def __start_playback(self) -> None:
        """Start the playback thread."""
        if not self._event_playback.is_set():
            self._event_playback.set()
            if self._show_frames_thread is not None:
                self._show_frames_thread.join(1)  # timeout is required to avoid problem with a wiggling navigation slider
                self._show_frames_thread = None
            self._show_frames_thread = threading.Thread(target=self._show_frames, name="_show_frames")
            self._show_frames_thread.daemon = True
            self._show_frames_thread.start()

    def __stop_playback(self) -> None:
        """Stop the playback thread."""
        if self._event_playback.is_set() and self._show_frames_thread:
            self._event_playback.clear()
            if self._show_frames_thread != threading.current_thread():
                self._show_frames_thread.join(1)  # timeout is required to avoid problem with a wiggling navigation slider
                self._show_frames_thread = None

    def _show_frames(self) -> None:
        """Thread that displays frames for playback."""
        last_shown_frame_index: int = -1

        if self.Player:
            try:
                while self._event_playback.is_set():
                    start_time = time.perf_counter()
                    try:
                        n_frame = self.TimeLine.get_frame()
                    except EOFError:
                        self.player_stop()
                        break
                    if n_frame is not None:
                        if n_frame.index != last_shown_frame_index:  # Check if frame really changed
                            self.Player.show_frame(n_frame.frame)
                            last_shown_frame_index = n_frame.index

                            if self.TimeLine.last_returned_index is None:
                                self._status("Time position", "There are no ready frames")
                            else:
                                self.position.set(self.TimeLine.last_returned_index)

                                if self.TimeLine.last_returned_index:
                                    self._status("Time position", seconds_to_hmsms(self.TimeLine.last_returned_index * self.metadata.frame_time))
                                    self._status("Frame position", f'{self.position.get()}/{self.metadata.frames_count}')

                    loop_time = time.perf_counter() - start_time  # Time for the current loop
                    sleep_time = self.metadata.frame_time - loop_time  # Time to wait for next loop

                    if sleep_time > 0:
                        time.sleep(sleep_time)
            finally:
                self.player_stop()

    def notification_handler(self, notification: NotificationMessage) -> None:
        """Incoming notifications handler"""
        match notification.type:
            case notification.NTF_FRAME:  # add frame index to timeline
                self.TimeLine.add_frame_index(notification.index)
                self._status("Average processing speed", f"{round(notification.fps, 4)} FPS")
                self.set_progress_index_value(notification.index, PROCESSED)
            case _:
                app_logger.info(f"Handler is not implemented for notification {notification.type}")

    @property
    def prepare_frames(self) -> bool:
        return self.ProcessingClient.get_prepare_frames()

    @prepare_frames.setter
    def prepare_frames(self, value: bool) -> None:
        """Set the value of _prepare_frames and update the parameters."""
        self.ProcessingClient.set_prepare_frames(value)
        self.reload_parameters()
