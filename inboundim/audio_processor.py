# =====================================================================
# Audio Processing Functions
# =====================================================================

from pathlib import Path
from typing import Optional
from config import logger
import subprocess
import requests


def convert_audio_to_wav(audio_path: Path) -> Optional[Path]:
    """
    Convert audio file to WAV format compatible with FreeSWITCH.
    """
    wav_path = audio_path.with_suffix(".wav")

    if audio_path.suffix.lower() == ".wav":
        return audio_path

    try:
        logger.info(f"Converting {audio_path} to {wav_path}")
        subprocess.call(
            [
                "ffmpeg",
                "-i",
                str(audio_path),
                "-ar",
                "8000",  # 8kHz sample rate (telephone quality)
                "-ac",
                "1",  # Mono audio
                "-f",
                "wav",  # WAV format
                str(wav_path),
                "-y",  # Overwrite if exists
            ]
        )

        return wav_path
    except Exception as e:
        logger.error(f"Error converting audio: {str(e)}")
        return None


def get_audio_duration(file_path: Path) -> float:
    """
    Get the duration of an audio file in seconds.
    """
    try:
        logger.debug(f"Getting duration for {file_path}")
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        duration = float(result.stdout.strip())
        logger.debug(f"Audio duration: {duration} seconds")

        return duration
    except Exception as e:
        logger.error(f"Error getting audio duration: {str(e)}")
        return 5.0  # Default duration fallback


def download_audio_to_path(audio_url: str, dest_dir: Path) -> str:
    """
    Download audio from URL to local file system.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_filename = audio_url.split("/")[-1]
    dest_path = dest_dir / local_filename

    logger.info(f"Downloading audio from {audio_url} to {dest_path}")

    try:
        with requests.get(audio_url, stream=True) as response:
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        logger.info(f"Download complete: {dest_path}")
    except Exception as e:
        logger.error(f"Error downloading audio file: {e}")
        raise

    return str(dest_path)
