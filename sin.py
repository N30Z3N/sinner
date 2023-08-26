#!/usr/bin/env python3
import signal
import sys
from argparse import Namespace

from sinner.Benchmark import Benchmark
from sinner.Parameters import Parameters
from sinner.Preview import Preview
from sinner.Core import Core
from sinner.Sinner import Sinner
from sinner.utilities import limit_resources
from tests.constants import target_mp4, source_jpg
from tests.test_run import threads_count


class Sin(Sinner):
    gui: bool
    benchmark: bool
    max_memory: int

    parameters: Namespace

    def __init__(self) -> None:
        if sys.version_info < (3, 10):
            raise Exception('Python version is not supported - please upgrade to 3.10 or higher.')
        signal.signal(signal.SIGINT, lambda signal_number, frame: quit())
        self.parameters = Parameters().parameters
        super().__init__(parameters=self.parameters)
        self.update_parameters(self.parameters)
        limit_resources(self.max_memory)

    def run(self) -> None:
        if self.gui:
            core = Core(parameters=self.parameters)
            preview = Preview(core)
            window = preview.show()
            window.mainloop()
        elif self.benchmark is True:
            Benchmark(parameters=self.parameters)
        else:
            Core(parameters=self.parameters).run()


if __name__ == '__main__':
    params = Parameters(f'--target-path="{target_mp4}" --source-path="{source_jpg}" --execution-treads={threads_count}  --frame-processor FaceSwapper FaceEnhancer')
    Core(parameters=params.parameters).buffered_run()
    # Sin().run()

