#!/usr/bin/env python3
import asyncio
import os
import time
import sys

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'  # do not flood with oneDNN spam

if sys.version_info < (3, 10):
    print('Python version is not supported - please upgrade to 3.10 or higher.')
    quit()

try:  # fixes incompatibility issue with outdated basicsr package
    import torchvision.transforms.functional_tensor  # noqa: F401
except ImportError:
    try:
        import torchvision.transforms.functional as functional

        sys.modules["torchvision.transforms.functional_tensor"] = functional
    except ImportError:
        pass  # shrug...

from sinner.AppLogger import setup_logging  # noqa: E402
import signal  # noqa: E402
from argparse import Namespace  # noqa: E402
from sinner.Benchmark import Benchmark  # noqa: E402
from sinner.Parameters import Parameters  # noqa: E402
from sinner.BatchProcessingCore import BatchProcessingCore  # noqa: E402
from sinner.Sinner import Sinner  # noqa: E402
from sinner.gui.GUIForm import GUIForm  # noqa: E402
from sinner.webcam.WebCam import WebCam  # noqa: E402
from sinner.utilities import limit_resources  # noqa: E402
from sinner.server.FrameProcessingServer import FrameProcessingServer  # noqa: E402


class Sin(Sinner):
    gui: bool
    server: bool
    benchmark: bool
    camera: bool
    max_memory: int

    parameters: Namespace

    def __init__(self) -> None:
        signal.signal(signal.SIGINT, lambda signal_number, frame: quit())
        signal.signal(signal.SIGTERM, lambda signal_number, frame: quit())
        self.parameters = Parameters().parameters
        super().__init__(parameters=self.parameters)
        self.update_parameters(self.parameters)
        limit_resources(self.max_memory)

    def run_server(self) -> None:
        """Main function to run the server."""
        # self.logger.info(f"Starting Frame Processor Server")

        # Create and start server
        server = FrameProcessingServer(self.parameters)

        # Start the server
        asyncio.run(server.start_server())
        # self.logger.info("Server started successfully")

        # Keep the script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            # self.logger.info("Interrupted by user")
            pass
        finally:
            server.stop_server()
            # self.logger.info("Server shut down")

    def run(self) -> None:
        setup_logging(handlers=self.log)
        if self.gui:
            preview = GUIForm(parameters=self.parameters)
            window = preview.show()
            window.mainloop()
        elif self.server:
            self.run_server()
        elif self.benchmark is True:
            Benchmark(parameters=self.parameters)
        elif self.camera is True:
            WebCam(parameters=self.parameters).run()
        else:
            BatchProcessingCore(parameters=self.parameters).run()


if __name__ == '__main__':
    # single thread doubles cuda performance - needs to be set before torch import
    if any(arg.startswith('--execution-provider') for arg in sys.argv):
        os.environ['OMP_NUM_THREADS'] = '1'
    Sin().run()
