"""Автоматическое скачивание ML-моделей при первом запуске."""
from __future__ import annotations

from pathlib import Path
from typing import Callable
import requests
from tqdm import tqdm

from config import MODELS_DIR, FACE_SWAP_MODEL_NAME


# Зеркало модели inswapper. Официальная распространялась через insightface,
# но из-за злоупотреблений авторы её отозвали. На HuggingFace есть зеркала.
INSWAPPER_URLS = [
    "https://huggingface.co/ezioruan/inswapper_128.onnx/resolve/main/inswapper_128.onnx",
    "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx",
]


def download_file(
    url: str,
    dest: Path,
    progress_cb: Callable[[int, int], None] | None = None,
) -> bool:
    """Скачивает файл с прогрессом. progress_cb(downloaded, total)."""
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            tmp = dest.with_suffix(dest.suffix + ".part")
            downloaded = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MiB
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
            tmp.rename(dest)
            return True
    except Exception as e:
        print(f"[downloader] Не удалось {url}: {e}")
        if dest.with_suffix(dest.suffix + ".part").exists():
            dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
        return False


def ensure_inswapper(progress_cb: Callable[[int, int], None] | None = None) -> Path:
    """Проверяет наличие inswapper_128.onnx, если нет — скачивает."""
    target = MODELS_DIR / FACE_SWAP_MODEL_NAME
    if target.exists() and target.stat().st_size > 100 * 1024 * 1024:
        return target

    for url in INSWAPPER_URLS:
        print(f"[downloader] Качаю {url}")
        if download_file(url, target, progress_cb):
            return target

    raise RuntimeError(
        "Не удалось скачать inswapper_128.onnx ни с одного из зеркал. "
        "Скачай вручную и положи в папку models/."
    )
