import os
import sys


def pytest_sessionstart(session):
    #  try to avoid tkl initialization errors while testing in GitHub CI
    if 'CI' in os.environ and 'DISPLAY' not in os.environ:
        os.environ.__setitem__('DISPLAY', ':1.0')


def pytest_configure(config):
    """
    Хук, который выполняется перед запуском любых тестов
    """
    try:  # fixes incompatibility issue with outdated basicsr package
        import torchvision.transforms.functional_tensor  # noqa: F401
    except ImportError:
        try:
            import torchvision.transforms.functional as functional
            sys.modules["torchvision.transforms.functional_tensor"] = functional
        except ImportError:
            pass  # shrug...
