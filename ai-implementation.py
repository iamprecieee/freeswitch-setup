"""
AI-Enhanced Calling System
--------------------------
This system creates an automated outbound calling solution with AI capabilities,
enabling natural conversation with callers through speech recognition,
natural language understanding, and high-quality voice synthesis.
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# Third-party dependencies
import ESL
import requests
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from google import generativeai as genai
from google.cloud import speech

# =====================================================================
# Configuration and Setup
# =====================================================================

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('freeswitch_caller')

# Load environment variables
load_dotenv("/home/admin/.env")

# Set up API credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    "/home/admin/totemic-effect-454322-d3-fb89e5de2a13.json"
)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# FreeSWITCH connection settings
FREESWITCH_HOST = os.getenv("FREESWITCH_HOST")
FREESWITCH_PORT = int(os.getenv("FREESWITCH_PORT"))
FREESWITCH_PASSWORD = os.getenv("FREESWITCH_PASSWORD")

# Call settings
CALLER_ID = os.getenv("CALLER_ID")
GATEWAY = os.getenv("GATEWAY")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

# Audio paths and settings
INITIAL_AUDIO_PATH = Path("/home/admin/Wav.1.m4a")
RECORDINGS_DIR = Path("/tmp/freeswitch_recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize API clients
eleven_labs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# =====================================================================
# Audio Processing Functions
# =====================================================================

def convert_audio_to_wav(audio_path: Path) -> Optional[Path]:
    """
    Convert audio file to WAV format compatible with FreeSWITCH.
    
    Args:
        audio_path: Path to the source audio file
        
    Returns:
        Path to the converted WAV file or None if conversion failed
    """
    wav_path = audio_path.with_suffix(".wav")
    
    if audio_path.suffix.lower() == ".wav":
        return audio_path
        
    try:
        logger.info(f"Converting {audio_path} to {wav_path}")
        subprocess.call([
            "ffmpeg", "-i", str(audio_path), 
            "-ar", "8000",  # 8kHz sample rate (telephone quality)
            "-ac", "1",     # Mono audio
            "-f", "wav",    # WAV format
            str(wav_path), "-y"  # Overwrite if exists
        ])
        
        return wav_path
    except Exception as e:
        logger.error(f"Error converting audio: {str(e)}")
        return None


def get_audio_duration(file_path: Path) -> float:
    """
    Get the duration of an audio file in seconds.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        Duration in seconds, or 5 seconds as fallback if detection fails
    """
    try:
        logger.debug(f"Getting duration for {file_path}")
        result = subprocess.run(
            ["ffprobe", "-v", "error", 
             "-show_entries", "format=duration", 
             "-of", "default=noprint_wrappers=1:nokey=1", 
             str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
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
    
    Args:
        audio_url: URL of the audio file to download
        dest_dir: Directory to save the downloaded file
        
    Returns:
        Local file path of the downloaded audio
        
    Raises:
        Exception: If download fails
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

# =====================================================================
# FreeSWITCH Call Management Functions
# =====================================================================

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

# =====================================================================
# AI Speech and Language Processing Functions
# =====================================================================

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio file to text using Google Cloud Speech-to-Text.
    
    Args:
        file_path: Path to the audio file to transcribe
        
    Returns:
        Transcribed text or empty string if transcription failed
    """
    try:
        speech_client = speech.SpeechClient()
        
        # Read the audio file
        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()
            audio = speech.RecognitionAudio(content=audio_data)
            
        # Configure the recognition request
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code='en-US'
        )
        
        # Perform the transcription
        response = speech_client.recognize(config=config, audio=audio)

        # Extract the transcript from the response
        transcript = response.results[0].alternatives[0].transcript
        logger.info(f"Transcript: {transcript}")
        
        return transcript

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return ""


def process_call_context(
    call_context: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    Process transcribed speech and get an AI-generated response.
    
    Args:
        call_context: Current transcribed user message
        conversation_history: Previous messages for context
        system_prompt: Custom instructions for the AI
        
    Returns:
        Generated AI response text
    """
    # Initialize empty history if none provided
    if conversation_history is None:
        conversation_history = []

    # Add current message to conversation context
    messages = conversation_history + [{"role": "user", "content": call_context}]
    
    # Generate response using Gemini
    response = send_message_to_gemini(
        messages=messages, 
        system_prompt=system_prompt
    )

    return response


def send_message_to_gemini(
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    model: str = "gemini-1.5-pro-latest"
) -> str:
    """
    Send conversation to Google Gemini AI and get a response.
    
    Args:
        messages: List of conversation messages with 'role' and 'content'
        system_prompt: Custom behavior instructions for the AI
        model: Gemini model identifier to use
        
    Returns:
        Generated AI response text
    """
    # Default personality and behavior instructions
    default_system_prompt = """
    You are an enthusiastic, engaging, and friendly AI guide. Your responses should be warm, 
    concise, and natural — like a helpful friend! Keep the conversation fun and approachable. 
    Do not use emojis and make your response seem non-ai generated.
    """

    # Combine default with custom instructions if provided
    final_system_prompt = (
        f"{default_system_prompt}\n\n{system_prompt}" 
        if system_prompt else default_system_prompt
    )

    # Convert messages to Gemini's format (list of text parts)
    message_texts = [msg["content"] for msg in messages]

    try:
        # Initialize model and generate response
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            [final_system_prompt] + message_texts
        )

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error calling Google Gemini API: {str(e)}")
        return "I'm sorry, I didn't quite catch that."


def convert_text_to_audio(text: str, call_uuid: str) -> str:
    """
    Convert text to spoken audio using ElevenLabs text-to-speech.
    
    Args:
        text: Text to convert to speech
        call_uuid: Call UUID for filename reference
        
    Returns:
        Path to the generated audio file
    """
    # Clean and normalize the text
    text = re.sub(r'\([^)]*\)', '', text)  # Remove text in parentheses
    formatted_text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    
    # Generate speech using ElevenLabs
    audio = eleven_labs_client.text_to_speech.convert(
        voice_id="RAVWJW17BPoSIf05iXxf",  # Voice identifier
        output_format="mp3_44100_128",    # High-quality audio format
        text=formatted_text,
        model_id="eleven_flash_v2_5",     # Optimized for low latency
    )
    
    # Save the audio to a file
    output_path = f"/tmp/freeswitch_recordings/output_{call_uuid}.wav"
    with open(output_path, "wb") as out:
        for chunk in audio:
            if chunk:
                out.write(chunk)
    
    logger.info(f'Audio content written to file "{output_path}"')
    return output_path

# =====================================================================
# Main Conversation Logic
# =====================================================================

def conversation_loop(
    conn: ESL.ESLconnection, 
    call_uuid: str, 
    entire_call_recording_path: Path, 
    max_iterations: int = 5
) -> None:
    """
    Manage the AI conversation loop with the caller.
    
    Records user speech, processes it with AI, generates responses,
    and plays them back to create a natural conversation flow.
    
    Args:
        conn: Active FreeSWITCH ESL connection
        call_uuid: UUID of the active call
        entire_call_recording_path: Path to save the complete call recording
        max_iterations: Maximum conversation turns to allow
    """
    iteration = 0
    conversation_history = []  # Tracks conversation for context

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"\n--- Conversation iteration {iteration}/{max_iterations} ---")
        
        # Check if call is still active
        if not check_call_active(conn, call_uuid):
            logger.warning("Call is no longer active, ending conversation loop")
            break
            
        # Step 1: Record user's spoken response
        recorded_response = record_user_response(conn, call_uuid)
        if not recorded_response:
            logger.info("No valid response recorded; ending conversation.")
            break
        
        # Verify call is still active after recording
        if not check_call_active(conn, call_uuid):
            logger.warning("Call hung up after recording, ending conversation")
            break
            
        # Step 2: Transcribe speech to text
        transcription = transcribe_audio(recorded_response)
        logger.info(f"Transcribed text: {transcription}")

        # Step 3: Update conversation history
        conversation_history.append({"role": "user", "content": transcription})

        # Step 4: Generate AI response
        logger.info("Processing with Gemini AI...")
        try:
            ai_response = process_call_context(
                call_context=transcription, 
                conversation_history=conversation_history
            )
        except Exception as e:
            logger.warning(f"Failed to get AI response: {str(e)}")
            continue
        
        logger.info(f"AI Response: {ai_response}")
        
        # Step 5: Update conversation history with AI response
        conversation_history.append({"role": "assistant", "content": ai_response})

        # Step 6: Convert response to speech
        logger.info("Converting AI response to audio...")
        try:
            audio_response = convert_text_to_audio(ai_response, call_uuid)
        except Exception as e:
            logger.warning(f"Failed to convert text to audio: {str(e)}")
            continue

        # Step 7: Play response back to caller
        logger.info("Playing AI response to caller...")
        try:
            play_audio_file(conn, call_uuid, audio_response)
        except Exception as e:
            logger.warning(f"Failed to play AI response: {str(e)}")
            continue

    # Conversation loop complete
    logger.info("Conversation loop ended after %d iterations", iteration)
    
    # Stop recording the entire call
    stop_entire_cmd = f"uuid_record {call_uuid} stop {entire_call_recording_path}"
    conn.api(stop_entire_cmd)
    logger.info(f"Stopped recording entire call: {entire_call_recording_path}")

    # Ensure the call is properly hung up
    if check_call_active(conn, call_uuid):
        time.sleep(1)  # Brief pause before hangup
        logger.info("Hanging up call")
        hangup_cmd = f"uuid_kill {call_uuid}"
        conn.api(hangup_cmd)


def main() -> None:
    """
    Main function to run the AI calling system.
    
    Handles setup, call initiation, and cleanup
    """
    # Process initial greeting audio
    if INITIAL_AUDIO_PATH.suffix.lower() != ".wav":
        audio_file = convert_audio_to_wav(INITIAL_AUDIO_PATH)
    else:
        audio_file = INITIAL_AUDIO_PATH

    if not audio_file or not Path(audio_file).exists():
        logger.error("Initial greeting audio file unavailable")
        return

    # Get audio duration for informational purposes
    audio_duration = get_audio_duration(audio_file)
    logger.info(f"Initial greeting duration: {audio_duration} seconds")

    # Initialize FreeSWITCH connection
    logger.info("Starting AI calling system...")
    logger.info(f"Connecting to FreeSWITCH at {FREESWITCH_HOST}:{FREESWITCH_PORT}...")

    conn = ESL.ESLconnection(FREESWITCH_HOST, FREESWITCH_PORT, FREESWITCH_PASSWORD)

    if not conn.connected():
        logger.error("Failed to connect to FreeSWITCH")
        return

    logger.info("Successfully connected to FreeSWITCH")
    
    # Subscribe to all events to monitor call progress
    conn.events("plain", "all")

    # Initiate the outbound call
    call_uuid = initiate_call(conn)
    if not call_uuid:
        logger.error("Call initiation failed")
        return

    logger.info(f"Call initiated with UUID: {call_uuid}")

    # Wait for call to be answered
    event_result = wait_for_call_events(conn)
    
    if event_result == "ANSWERED":
        # Set up call recording
        call_recording_filename = f"outbound_call_recording_{call_uuid}.wav"
        call_recording_path = RECORDINGS_DIR / call_recording_filename
        logger.info(f"Recording call to: {call_recording_path}...")
        
        call_record_cmd = f"uuid_record {call_uuid} start {call_recording_path}"
        conn.api(call_record_cmd)

        # Play initial greeting and start conversation if successful
        if play_audio_file(conn, call_uuid, audio_file):
            logger.info("Initial greeting played successfully")
            conversation_loop(conn, call_uuid, call_recording_path, max_iterations=3)
        else:
            logger.error("Failed to play initial greeting or call hung up")
    else:
        # Call wasn't answered, hang up
        logger.info("Call wasn't answered, cleaning up")
        hangup_cmd = f"uuid_kill {call_uuid}"
        conn.api(hangup_cmd)


if __name__ == "__main__":
    main()
