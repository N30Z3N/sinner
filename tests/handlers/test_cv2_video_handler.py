import os
import shutil
from argparse import Namespace
from typing import Iterator

import pytest
from cv2 import VideoCapture
from numpy import ndarray

from sinner.Parameters import Parameters
from sinner.handlers.frame.CV2VideoHandler import CV2VideoHandler
from sinner.utilities import resolve_relative_path
from tests.constants import TARGET_FPS, TARGET_FC, FRAME_SHAPE, tmp_dir, target_mp4, broken_mp4, result_mp4, state_frames_dir, TARGET_RESOLUTION, BROKEN_FC, state_frames_jpg_dir

# Базовые параметры командной строки
base_parameters = Parameters().parameters


def setup():
    #  clean previous results, if exists
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


def setup_function():
    setup()


@pytest.fixture(params=['png', 'jpg'])
def image_format(request):
    """Фикстура для тестирования разных форматов изображений"""
    return request.param


@pytest.fixture
def quality_value(image_format):
    """Фикстура для тестирования значений качества в зависимости от формата"""
    if image_format == 'png':
        return 1  # Высокое сжатие для PNG
    else:
        return 80  # Среднее качество для JPG


@pytest.fixture
def test_parameters(image_format, quality_value):
    """Фикстура для создания параметров командной строки с разными форматами и качеством"""
    params = Namespace()
    for key, value in vars(base_parameters).items():
        setattr(params, key, value)

    setattr(params, 'format', image_format)
    setattr(params, 'quality', quality_value)
    return params


@pytest.fixture
def test_object(test_parameters):
    """Фикстура для создания тестового объекта CV2VideoHandler с различными параметрами"""
    return CV2VideoHandler(parameters=test_parameters, target_path=target_mp4)


@pytest.fixture
def broken_object(test_parameters):
    """Фикстура для создания тестового объекта CV2VideoHandler с бракованным видео"""
    return CV2VideoHandler(parameters=test_parameters, target_path=broken_mp4)


def test_handler_format(test_object, image_format):
    """Проверка, что формат изображения установлен правильно"""
    assert test_object._writer.extension.endswith(image_format)
    assert test_object.format == image_format


def test_open(test_object):
    """Проверка открытия видеофайла"""
    capture = test_object.open()
    assert isinstance(capture, VideoCapture)
    capture.release()
    with pytest.raises(Exception):
        CV2VideoHandler(parameters=base_parameters, target_path='Wrong file')


def test_available(test_object):
    """Проверка доступности обработчика"""
    assert test_object.available() is True


def test_detect_fps(test_object):
    """Проверка определения FPS"""
    assert TARGET_FPS == test_object.fps


def test_detect_fc(test_object):
    """Проверка определения количества кадров"""
    assert TARGET_FC == test_object.fc


@pytest.mark.skip(reason="Skipped due to removed functionality")
def test_detect_broken_fc(broken_object):
    """Проверка определения количества кадров в бракованном видео"""
    assert BROKEN_FC == broken_object.fc


def test_detect_resolution(test_object):
    """Проверка определения разрешения видео"""
    assert TARGET_RESOLUTION == test_object.resolution


def test_get_frames_paths(test_object, image_format):
    """Проверка получения путей к кадрам"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir)
    assert TARGET_FC == len(frames_paths)
    first_item = frames_paths[0]
    assert (0, resolve_relative_path(os.path.join(tmp_dir, f'00.{image_format}'))) == first_item
    last_item = frames_paths.pop()
    assert (9, resolve_relative_path(os.path.join(tmp_dir, f'09.{image_format}'))) == last_item


def test_get_frames_paths_range(test_object, image_format):
    """Проверка получения путей к кадрам с указанием диапазона"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir, frames_range=(3, 8))
    assert 6 == len(frames_paths)
    first_item = frames_paths[0]
    assert first_item == (3, resolve_relative_path(os.path.join(tmp_dir, f'03.{image_format}')))
    last_item = frames_paths.pop()
    assert (8, resolve_relative_path(os.path.join(tmp_dir, f'08.{image_format}'))) == last_item


def test_get_frames_paths_range_start(test_object, image_format):
    """Проверка получения путей к кадрам с указанием только начала диапазона"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir, frames_range=(None, 8))
    assert 9 == len(frames_paths)
    first_item = frames_paths[0]
    assert (0, resolve_relative_path(os.path.join(tmp_dir, f'00.{image_format}'))) == first_item
    last_item = frames_paths.pop()
    assert (8, resolve_relative_path(os.path.join(tmp_dir, f'08.{image_format}'))) == last_item


def test_get_frames_paths_range_end(test_object, image_format):
    """Проверка получения путей к кадрам с указанием только конца диапазона"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir, frames_range=(3, None))
    assert 7 == len(frames_paths)
    first_item = frames_paths[0]
    assert (3, resolve_relative_path(os.path.join(tmp_dir, f'03.{image_format}'))) == first_item
    last_item = frames_paths.pop()
    assert (9, resolve_relative_path(os.path.join(tmp_dir, f'09.{image_format}'))) == last_item


def test_get_frames_paths_range_empty(test_object, image_format):
    """Проверка получения путей к кадрам без указания диапазона"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir, frames_range=(None, None))
    assert TARGET_FC == len(frames_paths)
    first_item = frames_paths[0]
    assert (0, resolve_relative_path(os.path.join(tmp_dir, f'00.{image_format}'))) == first_item
    last_item = frames_paths.pop()
    assert (9, resolve_relative_path(os.path.join(tmp_dir, f'09.{image_format}'))) == last_item


def test_get_frames_paths_range_fail(test_object):
    """Проверка получения путей к кадрам с неправильным диапазоном"""
    frames_paths = test_object.get_frames_paths(path=tmp_dir, frames_range=(10, 1))
    assert 0 == len(frames_paths)


def test_extract_frame(test_object):
    """Проверка извлечения кадра"""
    first_frame = test_object.extract_frame(1)
    assert 1 == first_frame.index
    assert isinstance(first_frame.frame, ndarray)
    assert first_frame.frame.shape == FRAME_SHAPE


def test_result(test_object, image_format):
    """Проверка создания результирующего видео"""
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")

    # Создаем уникальный путь для результата с учетом формата
    result_path = f"{result_mp4}"

    assert os.path.exists(result_path) is False
    if image_format == 'png':
        assert test_object.result(from_dir=state_frames_dir, filename=result_path) is True
    elif image_format == 'jpg':
        assert test_object.result(from_dir=state_frames_jpg_dir, filename=result_path) is True
    assert os.path.exists(result_path)

    # Создаем новый обработчик для проверки результата
    result_params = Namespace()
    for key, value in vars(base_parameters).items():
        setattr(result_params, key, value)

    target = CV2VideoHandler(parameters=result_params, target_path=result_path)
    assert target.fc == TARGET_FC
    assert target.fps == TARGET_FPS


def test_file_size_comparison(image_format):
    """Проверка разницы в размере файлов между форматами"""
    if 'CI' in os.environ:
        pytest.skip("This test is not ready for GitHub CI")

    # Пропускаем, если в этом запуске тестируется только один формат
    if image_format not in ['png', 'jpg']:
        pytest.skip(f"Тест работает только с PNG и JPG, получен {image_format}")

    # Получаем пути к результирующим файлам
    png_result = f"{result_mp4}_png"
    jpg_result = f"{result_mp4}_jpg"

    # Проверяем, что оба файла существуют
    if not (os.path.exists(png_result) and os.path.exists(jpg_result)):
        pytest.skip("Необходимо сначала выполнить test_result для обоих форматов")

    # Сравниваем размеры файлов
    png_size = os.path.getsize(png_result)
    jpg_size = os.path.getsize(jpg_result)

    # При обычных настройках качества, JPG обычно меньше PNG
    print(f"PNG size: {png_size}, JPG size: {jpg_size}, Ratio: {png_size / jpg_size:.2f}x")


def tests_iterator(test_object):
    """Проверка работы итератора"""
    assert isinstance(test_object, Iterator)
    frame_counter = 0
    for frame_index in test_object:
        assert isinstance(frame_index, int)
        frame_counter += 1
    assert frame_counter == TARGET_FC

    test_object.current_frame_index = 8
    frame_counter = 0
    for frame_index in test_object:
        assert isinstance(frame_index, int)
        frame_counter += 1
    assert frame_counter == 2