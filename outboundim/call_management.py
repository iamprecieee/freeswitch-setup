# =====================================================================
# FreeSWITCH Call Management Functions
# =====================================================================

from config import ESL, CALLER_ID, GATEWAY, PHONE_NUMBER, logger, RECORDINGS_DIR
from typing import Dict, List, Optional, Tuple, Union
import time
from audio_processor import download_audio_to_path, convert_audio_to_wav
from pathlib import Path
import subprocess


def initiate_call(conn: ESL.ESLconnection) -> Optional[str]:
    """
    Initiate an outbound call using FreeSWITCH.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        
    Returns:
        Call UUID if call initiated successfully, None otherwise
    """
    # Define variables for the outbound call
    origination_vars = {
        "absolute_codec_string": "PCMA",
        "ignore_early_media": "false",
        "origination_caller_id_number": CALLER_ID,
        "hangup_after_bridge": "false",
    }
    vars_string = ",".join([f"{k}={v}" for k, v in origination_vars.items()])
    
    # Build the originate command
    call_command = (
        f"originate {{{vars_string}}}"
        f"sofia/gateway/{GATEWAY}/{PHONE_NUMBER} "
        f"&park()"  # Park the call to maintain control
    )

    logger.info(f"Initiating call with command: {call_command}")
    
    # Execute the command and process the response
    result = conn.api(call_command)
    response = result.getBody().strip()
    
    logger.info(f"Call initiation result: {response}")

    # Extract UUID if call was successful
    if response.startswith("+OK"):
        call_uuid = response.split(" ", 1)[1]
        return call_uuid
    else:
        logger.error(f"Call initiation failed: {response}")
        return None


def wait_for_call_events(conn: ESL.ESLconnection, timeout: int = 5) -> Optional[str]:
    """
    Wait for call answer or hangup events within the specified timeout.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        timeout: Maximum seconds to wait for events
        
    Returns:
        "ANSWERED" if call is answered
        "HANGUP" if call is hungup/declined
        None if timeout expires with no relevant events
    """
    start_time = time.time()
    logger.info(f"Waiting up to {timeout} seconds for call events...")

    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(500)  # Poll every 0.5 seconds
        if event:
            event_name = event.getHeader("Event-Name")

            if event_name == "CHANNEL_ANSWER":
                logger.info(f"Event detected: {event_name}")
                logger.info("Call answered!")
                return "ANSWERED"
                
            elif event_name == "CHANNEL_HANGUP":
                logger.info(f"Event detected: {event_name}")
                hangup_cause = event.getHeader("Hangup-Cause") or "Unknown"
                logger.info(f"Call ended before answer. Hangup cause: {hangup_cause}")
                return "HANGUP"

    logger.warning("Timed out waiting for call events")
    return None


def play_audio_file(conn: ESL.ESLconnection, call_uuid: str, audio_file: Union[str, Path]) -> bool:
    """
    Play audio to an active call.
    
    Handles various audio sources including URLs and local files,
    ensuring proper format conversion if needed.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        call_uuid: UUID of the active call
        audio_file: Audio file path or URL
        
    Returns:
        True if playback completed successfully, False otherwise
    """
    # Handle URL audio sources
    if str(audio_file).startswith("http"):
        audio_file_path = download_audio_to_path(audio_file, RECORDINGS_DIR)
        audio_file = convert_audio_to_wav(Path(str(audio_file_path)))
    
    # Handle local file paths that need conversion
    if str(audio_file).startswith("/"):
        audio_file = convert_audio_to_wav(Path(str(audio_file)))
     
    logger.info(f"Playing audio: {audio_file}")
    play_cmd = f"uuid_broadcast {call_uuid} {audio_file} aleg"
    conn.api(play_cmd)
    
    # Wait for playback to complete
    return wait_for_playback_completion(conn, call_uuid)


def wait_for_playback_completion(conn: ESL.ESLconnection, call_uuid: str, timeout: int = 30) -> bool:
    """
    Wait for audio playback to complete or call to hang up.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        call_uuid: UUID of the active call
        timeout: Maximum seconds to wait for playback completion
        
    Returns:
        True if playback completed successfully, False otherwise
    """
    logger.info("Waiting for playback to complete...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(1000)  # Poll every 1 second
        if event:
            event_name = event.getHeader("Event-Name")      

            if event_name == "PLAYBACK_STOP":
                logger.info(f"Event detected: {event_name}")
                logger.info("Playback completed")
                return True
                
            elif event_name == "CHANNEL_HANGUP":
                logger.warning("Call hung up during playback")
                return False
    
    logger.warning(f"Playback timeout after {timeout} seconds")
    return False


def check_call_active(conn: ESL.ESLconnection, call_uuid: str) -> bool:
    """
    Check if a call is still active.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        call_uuid: UUID of the call to check
        
    Returns:
        True if call is active, False otherwise
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
    
    Args:
        conn: Active FreeSWITCH ESL connection
        call_uuid: UUID of the active call
        
    Returns:
        Path to the recorded audio file, or None if recording failed
    """
    recording_filename = f"client_response_{call_uuid}.wav"
    recording_path = RECORDINGS_DIR / recording_filename

    logger.info(f"Recording user's response to: {recording_path}")
    
    # Add a delay before recording to ensure any previous audio playback is complete
    time.sleep(2.0)
    
    # Start recording with these parameters:
    # - Maximum duration: 20 seconds (20000ms)
    # - Silence threshold: 50 (higher = less sensitive)
    # - Silence duration: 3 seconds (3000ms) to stop recording
    record_cmd = f"uuid_record {call_uuid} start {recording_path} 20000 50 3000"
    logger.debug(f"Recording command: {record_cmd}")
    conn.api(record_cmd)
    
    # Wait for recording events
    start_time = time.time()
    max_wait = 7  # 10 seconds max recording time
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
                
            elif event_name == "CHANNEL_HANGUP":
                logger.warning("Call hung up during recording")
                return None
    
    # If no RECORD_STOP event received, stop recording manually
    logger.info("Recording max time reached, stopping manually")
    stop_cmd = f"uuid_record {call_uuid} stop {recording_path}"
    conn.api(stop_cmd)
    
    # Validate the recording file
    if recording_path.exists():
        file_size = recording_path.stat().st_size
        logger.info(f"Recording completed. File size: {file_size} bytes")
        
        if file_size > 1000:  # Ensure file has meaningful content
            # Fix permissions to ensure FreeSWITCH can access the file
            subprocess.run(["sudo", "chown", "freeswitch:freeswitch", str(recording_path)])
            return recording_path
        else:
            logger.warning("Recording file is too small, likely empty")
            return None
    else:
        logger.warning("Recording file was not created")
        return None