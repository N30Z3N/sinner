# testing different run configurations
import glob
import multiprocessing
import os.path
import shutil

import pytest

from sinner.Parameters import Parameters
from sinner.BatchProcessingCore import BatchProcessingCore
from sinner.models.State import State
from sinner.processors.frame.DummyProcessor import DummyProcessor
from sinner.utilities import limit_resources, suggest_max_memory, get_file_name, get_app_dir, resolve_relative_path
from sinner.validators.LoaderException import LoadingException
from tests.constants import target_png, source_jpg, target_mp4, source_target_png, source_target_mp4, state_frames_dir, result_mp4, tmp_dir, result_png, TARGET_FC, images_dir, source_images_result

threads_count = multiprocessing.cpu_count()


def setup():
    #  clean previous results, if exists
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    if os.path.exists(source_target_png):
        os.remove(source_target_png)
    if os.path.exists(source_images_result):
        shutil.rmtree(source_images_result)
    if os.path.exists(source_target_mp4):
        os.remove(source_target_mp4)


def setup_function():
    setup()


def test_no_parameters() -> None:
    params = Parameters()
    limit_resources(suggest_max_memory())
    with pytest.raises(LoadingException):
        BatchProcessingCore(parameters=params.parameters).run()  # target path is fucked up


def test_no_source() -> None:
    params = Parameters(f'--target_path="{target_png}" --source_path=no_such_file')
    limit_resources(suggest_max_memory())
    with pytest.raises(LoadingException):
        BatchProcessingCore(parameters=params.parameters).run()  # source path is fucked up


def test_swap_image() -> None:
    assert os.path.exists(source_target_png) is False
    params = Parameters(f'--target-path="{target_png}" --source-path="{source_jpg}"')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(source_target_png) is True


def test_swap_mp4() -> None:
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")
    assert os.path.exists(source_target_mp4) is False
    params = Parameters(f'--target-path="{target_mp4}" --source-path="{source_jpg}" --execution-treads={threads_count}')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(source_target_mp4) is True


def test_swap_frames_to_mp4() -> None:
    assert os.path.exists(result_mp4) is False
    params = Parameters(f'--target-path="{state_frames_dir}" --source-path="{source_jpg}" --output-path="{result_mp4}" --execution-treads={threads_count}')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_mp4) is True


def test_swap_images() -> None:
    assert os.path.exists(source_images_result) is False
    original_images_names = [get_file_name(filepath) for filepath in glob.glob(os.path.join(images_dir, '*.jpg'))]
    params = Parameters(f'--target-path="{images_dir}" --source-path="{source_jpg}" --execution-treads={threads_count}')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(source_images_result) is True
    result_image_names = [get_file_name(filepath) for filepath in glob.glob(os.path.join(source_images_result, '*.*'))]
    assert sorted(original_images_names) == sorted(result_image_names)  # compare names without extensions


def test_enhance_image() -> None:
    assert os.path.exists(result_png) is False
    params = Parameters(f'--frame-processor=FaceEnhancer --target-path="{target_png}" --output-path="{result_png}"')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_png) is True


def test_swap_enhance_image() -> None:
    assert os.path.exists(result_png) is False
    params = Parameters(f'--frame-processor FaceSwapper FaceEnhancer --source-path="{source_jpg}" --target-path="{target_png}" --output-path="{result_png}" --execution-treads=16')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_png) is True


def test_swap_enhance_mp4() -> None:
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")
    assert os.path.exists(result_mp4) is False
    params = Parameters(f'--frame-processor FaceSwapper FaceEnhancer --source-path="{source_jpg}" --target-path="{target_mp4}" --output-path="{result_mp4}" --execution-treads={threads_count} --keep-frames --temp-dir="{tmp_dir}"')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_mp4) is True
    assert os.path.exists(os.path.join(tmp_dir, 'FaceSwapper/target.mp4/source.jpg', '09.png')) is True
    assert os.path.exists(os.path.join(tmp_dir, 'FaceEnhancer/target.mp4/source.jpg', '09.png')) is True


def test_swap_enhance_mp4_extract() -> None:
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")
    assert os.path.exists(result_mp4) is False
    params = Parameters(f'--frame-processor FaceSwapper FaceEnhancer --source-path="{source_jpg}" --target-path="{target_mp4}" --output-path="{result_mp4}" --extract-frames --execution-treads={threads_count}')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_mp4) is True


def test_dummy_mp4_extract_keep_frames() -> None:
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")
    assert os.path.exists(result_mp4) is False
    params = Parameters(f'--frame-processor DummyProcessor --target-path="{target_mp4}" --output-path="{result_mp4}" --extract-frames --keep-frames --temp-dir="{tmp_dir}"')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    assert os.path.exists(result_mp4) is True
    assert os.path.exists(os.path.join(tmp_dir, 'DummyProcessor', 'target.mp4')) is True
    assert len(glob.glob(os.path.join(tmp_dir, 'DummyProcessor', 'target.mp4', '*.png'))) == TARGET_FC


def test_set_execution_provider(capsys) -> None:
    assert os.path.exists(result_png) is False
    params = Parameters(f'--target-path="{target_png}" --source-path="{source_jpg}" --temp-dir="{tmp_dir}" --output-path="{result_png}" --execution-provider=cpu')
    limit_resources(suggest_max_memory())
    BatchProcessingCore(parameters=params.parameters).run()
    captured = capsys.readouterr()
    assert "Error Unknown Provider Type" not in captured.out
    assert os.path.exists(result_png) is True


def test_reprocess_lost_frames() -> None:
    case_temp_dir = resolve_relative_path('temp/DummyProcessor/frames/source.jpg', get_app_dir())
    assert os.path.exists(case_temp_dir) is False
    params = Parameters(f'--target-path="{state_frames_dir}" --source-path="{source_jpg}" --output-path="{result_mp4}" --execution-treads={threads_count}')

    batch_processor = BatchProcessingCore(parameters=params.parameters)

    current_processor = DummyProcessor(params.parameters)
    handler = batch_processor.suggest_handler(batch_processor.target_path, batch_processor.parameters)
    state = State(parameters=batch_processor.parameters, target_path=batch_processor.target_path, temp_dir=batch_processor.temp_dir, frames_count=handler.fc, processor_name='DummyProcessor')

    batch_processor.process(current_processor, handler, state)
    assert os.path.exists(case_temp_dir) is True
    assert len(glob.glob(os.path.join(case_temp_dir, '*.png'))) == 10
    os.remove(os.path.join(case_temp_dir, '05.png'))
    os.remove(os.path.join(case_temp_dir, '08.png'))
    assert len(glob.glob(os.path.join(case_temp_dir, '*.png'))) == 8
    batch_processor.process(current_processor, handler, state)
    assert len(glob.glob(os.path.join(case_temp_dir, '*.png'))) == 10
