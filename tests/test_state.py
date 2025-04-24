import os.path
import shutil
from argparse import Namespace
from typing import List

import pytest

from sinner.helpers.FrameHelper import EmptyFrame, create
from sinner.models.State import State
from sinner.models.NumberedFrame import NumberedFrame
from tests.constants import tmp_dir, target_mp4, source_jpg, target_png, TARGET_FC, state_frames_dir


def copy_files(from_dir: str, to_dir: str, filenames: List[str]) -> None:
    for file_name in filenames:
        source_path = os.path.join(from_dir, file_name)
        destination_path = os.path.join(to_dir, file_name)

        if os.path.isfile(source_path):
            shutil.copy2(source_path, destination_path)


def setup_function():
    setup()


def setup():
    #  clean previous results, if exists
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


@pytest.fixture(params=["png", "jpg"])
def image_format(request):
    """Фикстура для тестирования разных форматов изображений"""
    return request.param


@pytest.fixture
def quality_value(image_format):
    """Фикстура для тестирования значений качества в зависимости от формата"""
    if image_format == "png":
        return 3  # Средний уровень сжатия для PNG
    else:
        return 85  # Высокое качество для JPG


@pytest.fixture
def test_parameters(image_format, quality_value):
    """Фикстура для создания параметров с разными форматами и качеством"""
    params = Namespace()
    params.format = image_format
    params.quality = quality_value
    params.source = source_jpg
    return params


@pytest.fixture
def default_state(test_parameters):
    """Фикстура для создания объекта State с параметрами формата"""
    return State(
        parameters=test_parameters,
        target_path=target_mp4,
        temp_dir=tmp_dir,
        frames_count=TARGET_FC,
        processor_name="DummyProcessor"
    )


def test_raise_on_relative_path() -> None:
    """Проверка, что вызывается исключение при использовании относительного пути"""
    with pytest.raises(Exception):
        State(
            parameters=Namespace(),
            target_path=None,
            temp_dir="data/temp",
            frames_count=0,
            processor_name=""
        )


def test_handler_format(default_state, image_format):
    """Проверка, что формат изображения установлен правильно"""
    assert default_state._handler.extension.endswith(image_format)
    assert default_state.format == image_format


def test_handler_quality(default_state, image_format, quality_value):
    """Проверка, что качество изображения установлено правильно"""
    assert default_state.quality == quality_value
    if image_format == "png":
        assert default_state._handler.compression_level == quality_value
    else:
        assert default_state._handler.quality == quality_value


def test_basic(test_parameters, image_format) -> None:
    """Базовая проверка поведения класса State с учетом формата"""
    state = State(
        parameters=test_parameters,
        target_path=None,
        temp_dir=tmp_dir,
        frames_count=0,
        processor_name=""
    )

    assert os.path.exists(tmp_dir) is False
    assert state.source_path == source_jpg
    assert state.target_path is None
    assert state._temp_dir == tmp_dir  # используется абсолютный путь
    assert state.path == os.path.normpath(os.path.join(tmp_dir, os.path.basename(source_jpg)))

    assert os.path.exists(state.path) is True

    assert state.is_started is False
    assert state.is_finished is False

    assert state.processed_frames_count == 0
    assert state.zfill_length == 1

    # Проверка, что сгенерированное имя файла содержит правильное расширение
    processed_name = state.get_frame_processed_name(NumberedFrame(100, EmptyFrame))
    assert processed_name.endswith(f"100.{image_format}")
    assert processed_name.endswith(state._handler.extension)


def test_state_names_generation(test_parameters, image_format) -> None:
    """Проверка генерации имен файлов и директорий для состояния с учетом формата"""
    state = State(
        parameters=test_parameters,
        target_path=target_mp4,
        temp_dir=tmp_dir,
        frames_count=0,
        processor_name="DummyProcessor"
    )

    assert os.path.exists(os.path.join(tmp_dir, "DummyProcessor/target.mp4")) is False
    assert state.source_path == source_jpg
    assert state.target_path == target_mp4
    assert state._temp_dir == tmp_dir  # абсолютный путь
    assert state.path == os.path.abspath(os.path.join(tmp_dir, "DummyProcessor/target.mp4", os.path.basename(source_jpg)))

    assert os.path.exists(os.path.join(tmp_dir, "DummyProcessor/target.mp4")) is True

    state = State(parameters=Namespace(source=source_jpg), target_path=target_png, temp_dir=tmp_dir, frames_count=0, processor_name='DummyProcessor')
    assert os.path.exists(os.path.join(tmp_dir, 'DummyProcessor/target.png/source.jpg')) is False
    assert state.source_path == source_jpg
    assert state.target_path == target_png
    assert state._temp_dir == tmp_dir  # absolute path used
    assert state.path == os.path.abspath(os.path.join(tmp_dir, 'DummyProcessor/target.png/source.jpg'))
    assert os.path.exists(os.path.join(tmp_dir, 'DummyProcessor/target.png/source.jpg')) is True


def test_states(default_state, image_format) -> None:
    """Проверка различных состояний процесса обработки с учетом формата"""
    state = default_state
    extension = state._handler.extension
    assert extension.endswith(image_format)

    assert state.zfill_length == 2
    assert state.is_started is False
    assert state.is_finished is False
    assert state.processed_frames_count == 0
    assert state.unprocessed_frames_count == 10

    # Создаем тестовый кадр и сохраняем его
    frame = create((10, 10))
    state.save_temp_frame(NumberedFrame(0, frame))

    assert state.is_started is True
    assert state.is_finished is False
    assert state.processed_frames_count == 1
    assert state.unprocessed_frames_count == 9

    # Сохраняем еще несколько кадров
    for i in range(1, 5):
        state.save_temp_frame(NumberedFrame(i, frame))

    assert state.is_started is True
    assert state.is_finished is False
    assert state.processed_frames_count == 5
    assert state.unprocessed_frames_count == 5

    # Сохраняем оставшиеся кадры
    for i in range(5, 10):
        state.save_temp_frame(NumberedFrame(i, frame))

    assert state.is_started is False
    assert state.is_finished is True
    assert state.processed_frames_count == 10
    assert state.unprocessed_frames_count == 0


def test_final_check_ok(default_state, image_format):
    """Проверка успешного завершения проверки целостности"""
    state = default_state

    # Создаем и сохраняем тестовые кадры
    frame = create((10, 10))
    for i in range(TARGET_FC):
        state.save_temp_frame(NumberedFrame(i, frame))

    assert state.final_check() == (True, [])


def test_final_check_fail_state(default_state, image_format):
    """Проверка обнаружения отсутствующего кадра"""
    state = default_state
    extension = state._handler.extension

    # Создаем и сохраняем тестовые кадры, пропуская один
    frame = create((10, 10))
    for i in range(TARGET_FC):
        if i != 5:  # Пропускаем кадр 5
            state.save_temp_frame(NumberedFrame(i, frame))

    result, missing_frames = state.final_check()
    assert result is False
    assert 5 in missing_frames


def test_final_check_fail_zero_files(default_state, image_format):
    """Проверка обнаружения пустого файла"""
    state = default_state
    extension = state._handler.extension

    # Создаем и сохраняем тестовые кадры
    frame = create((10, 10))
    for i in range(TARGET_FC):
        state.save_temp_frame(NumberedFrame(i, frame))

    # Создаем пустой файл вместо одного из кадров
    frame_path = state.get_frame_processed_name(NumberedFrame(4, EmptyFrame))
    with open(frame_path, 'wb') as f:
        f.truncate(0)

    assert state.final_check() == (False, [])


def test_different_formats_compatibility():
    """Проверка, что можно сохранять и проверять файлы в разных форматах"""
    # Создаем состояние с PNG
    png_params = Namespace(format="png", quality=3, source=source_jpg)
    png_state = State(
        parameters=png_params,
        target_path=target_mp4,
        temp_dir=os.path.join(tmp_dir, "png_test"),
        frames_count=TARGET_FC,
        processor_name="PNGTest"
    )

    # Создаем состояние с JPG
    jpg_params = Namespace(format="jpg", quality=85, source=source_jpg)
    jpg_state = State(
        parameters=jpg_params,
        target_path=target_mp4,
        temp_dir=os.path.join(tmp_dir, "jpg_test"),
        frames_count=TARGET_FC,
        processor_name="JPGTest"
    )

    # Создаем тестовый кадр
    frame = create((100, 100))

    # Сохраняем один и тот же кадр в обоих форматах
    png_state.save_temp_frame(NumberedFrame(0, frame))
    jpg_state.save_temp_frame(NumberedFrame(0, frame))

    # Проверяем, что файлы действительно созданы с правильными расширениями
    png_path = png_state.get_frame_processed_name(NumberedFrame(0, EmptyFrame))
    jpg_path = jpg_state.get_frame_processed_name(NumberedFrame(0, EmptyFrame))

    assert os.path.exists(png_path)
    assert os.path.exists(jpg_path)
    assert png_path.endswith(".png")
    assert jpg_path.endswith(".jpg")

    # Дополнительно проверяем, что обработчики имеют правильные расширения
    assert png_state._handler.extension == ".png"
    assert jpg_state._handler.extension == ".jpg"

    # Проверяем размеры файлов
    png_size = os.path.getsize(png_path)
    jpg_size = os.path.getsize(jpg_path)

    print(f"PNG size: {png_size}, JPG size: {jpg_size}, Ratio: {png_size / jpg_size:.2f}x")

    # В обычных условиях, PNG файл будет больше, чем JPG при одинаковом содержимом
    # Но для очень простых изображений это может быть не так
    assert png_size != jpg_size, "Файлы разных форматов должны иметь разный размер"
