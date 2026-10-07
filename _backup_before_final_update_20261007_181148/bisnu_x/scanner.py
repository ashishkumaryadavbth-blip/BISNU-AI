from __future__ import annotations

import io
from pathlib import Path
import uuid

from PIL import Image

from bisnu_x.config import ROOT, settings


ALLOWED = {
    "image/jpeg",
    "image/png",
    "image/webp"
}


def save_image(
    filename: str,
    data: bytes
):
    max_bytes = (
        settings.max_upload_mb
        * 1024
        * 1024
    )

    if len(data) > max_bytes:
        raise ValueError(
            "Image is larger than the allowed upload size."
        )

    try:
        image = Image.open(
            io.BytesIO(data)
        )

        image.verify()

        image = Image.open(
            io.BytesIO(data)
        )
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Unsupported image format.")
        if image.width * image.height > 40_000_000:
            raise ValueError("Image dimensions exceed the processing limit.")
        image.load()

    except Exception as exc:
        raise ValueError(
            "Invalid image."
        ) from exc

    extension = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp"
    }.get(
        image.format,
        ".img"
    )

    directory = (
        Path(settings.upload_dir)
        if Path(
            settings.upload_dir
        ).is_absolute()
        else ROOT / settings.upload_dir
    )

    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    stored_name = (
        str(uuid.uuid4())
        + extension
    )

    target = directory / stored_name

    target.write_bytes(
        data
    )

    return {
        "filename": filename,
        "stored_file": stored_name,
        "size": len(data),
        "width": image.width,
        "height": image.height,
        "format": image.format,
        "vision_engine": "not_installed",
        "status":
            "image validated and stored"
    }
