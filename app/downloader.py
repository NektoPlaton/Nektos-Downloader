from pathlib import Path

import yt_dlp
import sys
import os


DOWNLOAD_DIR = Path("downloads")

if getattr(sys, "frozen", False):
    FFMPEG_DIR = Path(sys._MEIPASS) / "assets" / "ffmpeg"
else:
    FFMPEG_DIR = Path("assets") / "ffmpeg"


class DownloadCancelled(Exception):
    """Пользователь отменил скачивание."""


def get_video_info(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def get_video_formats(url: str) -> list[dict]:
    info = get_video_info(url)
    formats = []

    for fmt in info.get("formats", []):
        height = fmt.get("height")
        ext = fmt.get("ext")

        if height and ext:
            formats.append({
                "height": height,
                "ext": ext,
                "format_id": fmt.get("format_id"),
            })

    return formats


def format_speed(speed) -> str:
    """Безопасно превращает скорость в текст."""
    if not isinstance(speed, (int, float)) or speed <= 0:
        return "--"

    units = ["Б/с", "КБ/с", "МБ/с", "ГБ/с"]
    value = float(speed)
    unit_index = 0

    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    return f"{value:.1f} {units[unit_index]}"


def format_eta(eta) -> str:
    """Безопасно превращает ETA в текст."""
    if not isinstance(eta, (int, float)) or eta < 0:
        return "--"

    eta = int(eta)

    if eta >= 3600:
        return f"{eta // 3600}ч {(eta % 3600) // 60}м"

    if eta >= 60:
        return f"{eta // 60}м {eta % 60}с"

    return f"{eta}с"


def remove_partial_files(file_paths: set[str]) -> None:
    """
    Удаляет известные временные файлы.

    yt-dlp может создавать filename, filename.part и filename.ytdl.
    """
    for filename in file_paths:
        if not filename:
            continue

        variants = [
            filename,
            f"{filename}.part",
            f"{filename}.ytdl",
        ]

        for path_string in variants:
            path = Path(path_string)

            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass


def download_video(
    url: str,
    quality: str,
    download_dir: Path | str | None = None,
    progress_callback=None,
    cancel_callback=None,
    resume: bool = False,
) -> tuple[bool, set[str]]:
    """
    Скачивает выбранное качество.

    download_dir:
        Папка, в которую сохраняется видео.
        Если не передана — используется папка downloads.

    progress_callback принимает:
    - percent: float от 0 до 100
    - speed_text: str
    - eta_text: str

    resume=True → продолжаем предыдущую загрузку (continuedl=True).

    Возвращает:
    - was_cancelled: bool
    - created_files: set[str]
    """
    height = int(quality.replace("p", ""))

    if download_dir is None:
        output_dir = DOWNLOAD_DIR
    else:
        output_dir = Path(download_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    created_files: set[str] = set()
    was_cancelled = False

    def progress_hook(data: dict) -> None:
        nonlocal was_cancelled

        status = data.get("status")

        filename = data.get("filename")
        if filename:
            created_files.add(filename)

        if cancel_callback and cancel_callback():
            was_cancelled = True
            raise DownloadCancelled("Скачивание отменено")

        if status != "downloading":
            return

        downloaded = data.get("downloaded_bytes")
        total = data.get("total_bytes") or data.get("total_bytes_estimate")

        try:
            downloaded = float(downloaded or 0)
            total = float(total or 0)
        except (TypeError, ValueError):
            downloaded = 0
            total = 0

        percent = 0.0
        if total > 0:
            percent = min(100.0, max(0.0, downloaded / total * 100))

        speed_text = format_speed(data.get("speed"))
        eta_text = format_eta(data.get("eta"))

        if progress_callback:
            progress_callback(percent, speed_text, eta_text)

    options = {
        "ffmpeg_location": str(FFMPEG_DIR),
        "format": (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]"
        ),

        # Именно здесь задаётся выбранная пользователем папка.
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),

        # При resume=True yt-dlp продолжает .part-файлы в той же папке.
        "continuedl": resume,

        "nopart": False,

        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

    except DownloadCancelled:
        # При «Стоп» ничего не удаляем:
        # .part нужен для последующего «Продолжить».
        return True, created_files

    except Exception:
        # Ошибку передаст DownloadThread в окно.
        # Временные файлы оставляем: повторный запуск сможет их продолжить.
        raise

    return False, created_files