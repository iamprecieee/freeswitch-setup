# =====================================================================
# FreeSWITCH Call Management Functions
# =====================================================================

from config import ESL, RECORDINGS_DIR, logger
from typing import Union, Optional
from pathlib import Path
from audio_processor import (
    convert_audio_to_wav,
    get_audio_duration,
)
import time


def play_audio_file(
    conn: ESL.ESLconnection, call_uuid: str, audio_file: Union[str, Path]
) -> bool:
    """
    Play audio with improved reliability using direct playback.
    """
    # First verify call is still active
    if not check_call_active(conn, call_uuid):
        logger.error(f"Call {call_uuid} not active, cannot play audio")
        return False

    # Handle file conversion
    if isinstance(audio_file, (str, Path)) and str(audio_file).startswith("/"):
        audio_file = convert_audio_to_wav(Path(str(audio_file)))

    # Ensure file exists
    if not Path(audio_file).exists():
        logger.error(f"Audio file {audio_file} does not exist")
        return False

    # Use streamfile for more reliable playback
    conn.execute("playback", str(audio_file))

    # Wait based on audio duration
    duration = get_audio_duration(Path(audio_file))
    logger.info(f"Waiting {duration + 1} seconds for playback to complete")
    time.sleep(duration + 1)


def check_call_active(conn: ESL.ESLconnection, call_uuid: str) -> bool:
    """
    Check if a call is still active.
    """
    check_cmd = f"uuid_exists {call_uuid}"
    result = conn.api(check_cmd)
    response = result.getBody().strip()

    return response == "true"


def record_user_response(conn: ESL.ESLconnection, call_uuid: str) -> Optional[Path]:
    """
    Record caller's voice response with silence detection.

    Records audio from the call until silence is detected or
    maximum recording duration is reached.
    """
    recording_filename = f"client_response_{call_uuid}.wav"
    recording_path = RECORDINGS_DIR/recording_filename

    logger.info(f"Recording user's response to: {recording_path}")

    # Start recording with these parameters:
    # - Maximum duration: 15 seconds (15000ms)
    # - Silence threshold: 50 (higher = less sensitive)
    # - Silence duration: 3 seconds (3000ms) to stop recording
    record_cmd = f"uuid_record {call_uuid} start {recording_path} 15000 30 3000"
    logger.debug(f"Recording command: {record_cmd}")
    conn.api(record_cmd)

    # Wait for recording events
    start_time = time.time()
    max_wait = 15  # 15 seconds max recording time (including silence detection)
    record_started = False

    # Monitor recording events
    while time.time() - start_time < max_wait:
        event = conn.recvEventTimed(500)  # Poll every 0.5 seconds
        if event:
            event_name = event.getHeader("Event-Name")
            logger.debug(f"Recording event: {event_name}")

            if event_name == "RECORD_START":
                record_started = True
                logger.info("Recording started")

            elif event_name == "RECORD_STOP" and record_started:
                logger.info("Recording stopped automatically (silence detected)")
                return recording_path

    # If no RECORD_STOP event received, stop recording manually
    logger.info("Recording max time reached, stopping manually")
    stop_cmd = f"uuid_record {call_uuid} stop {recording_path}"
    conn.api(stop_cmd)

    # Validate the recording file
    if recording_path.exists():
        file_size = recording_path.stat().st_size
        logger.info(f"Recording completed. File size: {file_size} bytes")

        if file_size > 1000:  # Ensure file has meaningful content
            return recording_path
        else:
            logger.warning("Recording file is too small, likely empty")
            return None
    else:
        logger.warning("Recording file was not created")
        return None
