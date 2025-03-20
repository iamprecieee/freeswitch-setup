import ESL
import logging
import os
from pathlib import Path
import subprocess
import time
import requests
from dotenv import load_dotenv
from io import BytesIO
import re
from elevenlabs.client import ElevenLabs

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('freeswitch_caller')

load_dotenv(".env")

FREESWITCH_HOST = os.getenv("FREESWITCH_HOST")
FREESWITCH_PORT = int(os.getenv("FREESWITCH_PORT"))
FREESWITCH_PASSWORD = os.getenv("FREESWITCH_PASSWORD")

CALLER_ID = os.getenv("CALLER_ID")
GATEWAY = os.getenv("GATEWAY")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

INITIAL_AUDIO_PATH = Path("/home/admin/Wav.1.m4a")

# Directory to store recordings
RECORDINGS_DIR = Path("/tmp/freeswitch_recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Eleven Labs client
client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

GOOEY_API_KEY = os.getenv("GOOEY_API_KEY")

def initiate_call(conn):
    """
    Initiate an outbound call using FreeSWITCH's originate command.
    Returns the call UUID if initiated successfully.
    """

    origination_vars = {
        "origination_caller_id_number": CALLER_ID,
        "hangup_after_bridge": "false",
    }
    vars_string = ",".join([f"{k}={v}" for k, v in origination_vars.items()])
    
    call_command = (
        f"originate {{{vars_string}}}"
        f"sofia/gateway/{GATEWAY}/{PHONE_NUMBER} "
        f"&park()"
    )

    logger.info(f"Initiating call with command: {call_command}")
    
    result = conn.api(call_command)
    response = result.getBody().strip()
    
    logger.info(f"Call initiated successfully")
    logger.info(response)

    if response.startswith("+OK"):
        call_uuid = response.split(" ", 1)[1]
        return call_uuid
    else:
        return None


def wait_for_call_events(conn, timeout=5):
    """
    Wait for the CHANNEL_ANSWER event or a CHANNEL_HANGUP event within the given timeout.
    Returns:
      - "ANSWERED" if the call is answered.
      - "HANGUP" if the call is hung up (or declined) before being answered.
      - None if the timeout expires.
    """
    start_time = time.time()
    logger.info(f"Waiting up to {timeout} seconds for call events...")

    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(500)  # Wait for 0.5 second for events
        if event:
            event_name = event.getHeader("Event-Name")

            if event_name == "CHANNEL_ANSWER":
                # Wait for either answer or hangup events
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

def convert_audio_to_wav(audio_path):
    """
    Convert M4A to WAV for FreeSWITCH playback.
    """
    wav_path = audio_path.with_suffix(".wav")
    try:
        logger.info(f"Converting {audio_path} to {wav_path}")
        subprocess.call([
            "ffmpeg", "-i", str(audio_path),
            "-ar", "8000", "-ac", "1",
            "-f", "wav", str(wav_path), "-y"
        ])
        return wav_path
    except Exception as e:
        logger.error(f"Error converting audio: {str(e)}")
        return None

def get_audio_duration(file_path):
    """
    Get the duration of an audio file in seconds using ffprobe.
    """
    try:
        logger.debug(f"Getting duration for {file_path}")
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        duration = float(result.stdout.strip())
        logger.debug(f"Audio duration: {duration} seconds")
        return duration
    except Exception as e:
        logger.error(f"Error getting audio duration: {str(e)}")
        return 5  # Default duration if cannot determine

def download_audio(audio_url: str, dest_dir: Path) -> str:
    """
    Downloads an audio file from the given URL to the destination directory.
    Returns the local file path as a string.
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

def play_audio_file(conn, call_uuid, audio_file):
    """
    Play the initial greeting audio to the call using uuid_broadcast.
    If the provided audio_file is a URL, it will be downloaded first.
    """
    # Check if audio_file is a URL and download it if so
    if str(audio_file).startswith("http"):
        audio_file_path = download_audio(audio_file, RECORDINGS_DIR)
        audio_file = convert_audio_to_wav(Path(str(audio_file_path)))
     
    logger.info(f"Playing initial greeting: {audio_file}")
    play_cmd = f"uuid_broadcast {call_uuid} {audio_file} aleg"
    conn.api(play_cmd)
    
    # Wait for playback to complete instead of using a fixed delay
    return wait_for_playback_completion(conn, call_uuid)

def wait_for_playback_completion(conn, call_uuid, timeout=30):
    """
    Wait for the PLAYBACK_STOP event to signal audio playback has completed.
    Returns True if playback completed successfully, False otherwise.
    """
    logger.info("Waiting for playback to complete...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(1000)  # Wait for 1 second for events
        if event:
            event_name = event.getHeader("Event-Name")      

            if event_name == "PLAYBACK_STOP":
                logger.info(f"Event detected: {event_name}")
                logger.info("Playback completed")
                return True
            elif event_name == "CHANNEL_HANGUP":
                logger.warning("Call hung up during playback")
                return False
    
    logger.warning("Timeout waiting for playback completion")
    return False

def check_call_active(conn, call_uuid):
    """
    Check if a call is still active by using uuid_exists.
    Returns True if the call is active, False otherwise.
    """
    check_cmd = f"uuid_exists {call_uuid}"
    result = conn.api(check_cmd)
    response = result.getBody().strip()
    return response == "true"

def record_user_response(conn, call_uuid):
    """
    Record the user's response using uuid_record with more lenient silence detection.
    """
    recording_filename = f"client_response_{call_uuid}.wav"
    recording_path = RECORDINGS_DIR / recording_filename

    logger.info(f"Recording user's response to: {recording_path}")
    
    # Add a small delay before starting recording to ensure audio playback is fully complete
    time.sleep(2.0)
    
    record_cmd = f"uuid_record {call_uuid} start {recording_path} 20000 30 3000"
    logger.debug(f"Recording command: {record_cmd}")
    conn.api(record_cmd)
    
    # Wait for recording events
    start_time = time.time()
    max_wait = 5
    record_started = False
    
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
        
    # If no RECORD_STOP event, manually stop recording
    logger.info("Recording timed out, stopping manually")
    stop_cmd = f"uuid_record {call_uuid} stop {recording_path}"
    conn.api(stop_cmd)
    
    # Check if the file exists and has content
    if recording_path.exists():
        file_size = recording_path.stat().st_size
        logger.info(f"Recording completed. File size: {file_size} bytes")
        if file_size > 1000:  # Adjust minimum size threshold as needed
            subprocess.run(["sudo", "chown", "freeswitch:freeswitch", str(recording_path)])
            return recording_path
        else:
            logger.warning("Recording file is too small, may be empty")
            return None
    else:
        logger.warning("Recording file was not created")
        return None

def transcribe_audio(file_path: str) -> str:
    """Transcribes an audio file using Eleven Labs API."""
    try:
        with open(file_path, "rb") as audio_file:
            audio_data = BytesIO(audio_file.read())

        transcription = client.speech_to_text.convert(
            file=audio_data,
            model_id="scribe_v1",
        )
        return transcription.text

    except Exception as e:
        print(f"Error during transcription: {e}")
        return ""

def convert_text_to_audio(text):
    """Takes in transcribed audio text and returns an audio url"""
    text = re.sub(r'\([^)]*\)', '', text)
    formatted_text = re.sub(r'\s+', ' ', text).strip()

    payload = {
        "text_prompt": f"{formatted_text}",
        "azure_voice_name": "en-NG-AbeoNeural",
    }
    
    response = requests.post(
        "https://api.gooey.ai/v2/TextToSpeech",
        headers={
            "Authorization": "bearer " + GOOEY_API_KEY,
        },
        json=payload,
    )
    
    result = response.json()["output"]["audio_url"]
    return result
  

def conversation_loop(conn, call_uuid, entire_call_recording_path, max_iterations=5):
    """
    Continuously record the user's response, process it, and play the AI response.
    The loop continues until a maximum number of iterations is reached or
    no meaningful response is recorded.
    """
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        logger.info(f"\n--- Conversation iteration {iteration} ---")
        
        # First check if call is still active
        if not check_call_active(conn, call_uuid):
            logger.warning("Call is no longer active, ending conversation loop")
            break
            
        # Record user response
        recorded_response = record_user_response(conn, call_uuid)
        
        # Check if we got a valid recording
        if not recorded_response:
            logger.info("No valid response recorded; ending conversation.")
            break
        
        # Check if call is still active after recording
        if not check_call_active(conn, call_uuid):
            logger.warning("Call hung up after recording, ending conversation loop")
            break
            
        # Process the response
        transcription = transcribe_audio(recorded_response)
        logger.info(f"transcribed text: {transcription}")
        
        logger.info("Converting transcription to audio")
        try:
            audio_response = convert_text_to_audio(transcription)
        except Exception as e:
            logger.warning(f"Failed to convert text to audio: {str(e)}")
            continue

        logger.info("Playing audio response to client")
        try:
            play_audio_file(conn, call_uuid, audio_response)
        except Exception as e:
            logger.warning(f"Failed to play audio response to client: {str(e)}")
            continue

    logger.info("Conversation loop ended.")
    
    # Stop recording the entire call
    stop_entire_cmd = f"uuid_record {call_uuid} stop {entire_call_recording_path}"
    conn.api(stop_entire_cmd)
    logger.info(f"Stopped recording entire call: {entire_call_recording_path}")

    # Ensure the call is hung up
    if check_call_active(conn, call_uuid):
        time.sleep(1)
        logger.info("Hanging up call")
        hangup_cmd = f"uuid_kill {call_uuid}"
        conn.api(hangup_cmd)


if __name__ == "__main__":
    # Convert the file to WAV if needed
    if INITIAL_AUDIO_PATH.suffix.lower() != ".wav":
        audio_file = convert_audio_to_wav(INITIAL_AUDIO_PATH)
    else:
        audio_file = INITIAL_AUDIO_PATH

    if not audio_file or not audio_file.exists():
        logger.error("Audio file for greeting is not available.")
        exit(1)

    # Get the duration for informational purposes
    audio_duration = get_audio_duration(audio_file)

    logger.info("Starting freeswitch call script")
    
    # Connect to freeswitch using ESL
    logger.info(f"Connecting to freeswitch at {FREESWITCH_HOST}:{FREESWITCH_PORT}")

    conn = ESL.ESLconnection(FREESWITCH_HOST, FREESWITCH_PORT, FREESWITCH_PASSWORD)

    if not conn.connected():
        logger.error("Failed to connect to freeswitch")
        exit(1)

    logger.info("Successfully connected to FreeSWITCH")
    
    # Subscribe to all events to capture call events
    conn.events("plain", "all")

    # Initiate the call and obtain the call UUID
    call_uuid = initiate_call(conn)
    
    if not call_uuid:
        logger.error("Call initiation failed.")
        exit(1)

    logger.info(f"Call initiated with UUID: {call_uuid}")

    # Wait for either answer or hangup events
    event_result = wait_for_call_events(conn)
    
    if event_result == "ANSWERED":
        call_recording_filename = f"outbound_call_recording_{call_uuid}.wav"
        call_recording_path = RECORDINGS_DIR / call_recording_filename
        logger.info(f"Initiating entire call recording to: {call_recording_path}")
        
        call_record_cmd = f"uuid_record {call_uuid} start {call_recording_path}"
        conn.api(call_record_cmd)

        if play_audio_file(conn, call_uuid, audio_file):
            logger.info("Initial greeting played successfully, continuing with conversation")
            
            # Enter the conversation loop: record, process, and play response repeatedly
            conversation_loop(conn, call_uuid, call_recording_path, max_iterations=3)
        else:
            logger.error("Failed to play initial greeting or call hung up")
    else:
        logger.info("Hanging up call")
    
        hangup_cmd = f"uuid_kill {call_uuid}"
        conn.api(hangup_cmd)

    exit(0)
