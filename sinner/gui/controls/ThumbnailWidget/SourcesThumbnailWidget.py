from typing import Callable, Optional, Any

from PIL import Image

from sinner.gui.controls.ThumbnailWidget.BaseThumbnailWidget import BaseThumbnailWidget
from sinner.gui.controls.ThumbnailWidget.ThumbnailData import ThumbnailData
from sinner.utilities import is_image, get_file_name, normalize_path


class SourcesThumbnailWidget(BaseThumbnailWidget):

    def add_thumbnail(self, source_path: str, click_callback: Optional[Callable[[str], None]] = None) -> None:
        """
        Adds an image thumbnail to the widget
        :param source_path: image file path
        :param click_callback: on thumbnail click callback. None: global callback will be used
        """
        if is_image(source_path):
            super().add_thumbnail(source_path, click_callback)

    def _prepare_thumbnail_data(self, source_path: str, click_callback: Optional[Callable[[str], None]] = None) -> Optional[ThumbnailData]:
        """
        Prepare thumbnail data in background thread
        """
        source_path = str(normalize_path(source_path))
        thumbnail = self.get_cached_thumbnail(source_path)
        if not thumbnail:
            with Image.open(source_path) as img:
                thumbnail = self.get_thumbnail(img, self.thumbnail_size)
                pixel_count: Optional[int] = img.size[0] * img.size[1]
            self.set_cached_thumbnail(source_path, thumbnail, caption=get_file_name(source_path), pixel_count=pixel_count)
        pixel_count_raw: Any = thumbnail.info.get("pixel_count")
        pixel_count = int(pixel_count_raw) if pixel_count_raw else None
        caption = thumbnail.info.get("caption") or get_file_name(source_path)
        if pixel_count is None:
            with Image.open(source_path) as img:
                pixel_count = img.size[0] * img.size[1]
        return ThumbnailData(
            thumbnail=thumbnail,
            path=source_path,
            caption=caption,
            click_callback=click_callback,
            pixel_count=pixel_count
        )
