"""
AI-Enhanced Calling System
--------------------------
This system creates an automated outbound calling solution with AI capabilities,
enabling natural conversation with callers through speech recognition,
natural language understanding, and high-quality voice synthesis.
"""

from config import INITIAL_AUDIO_PATH, logger,FREESWITCH_HOST, FREESWITCH_PASSWORD, FREESWITCH_PORT, ESL, RECORDINGS_DIR
from audio_processor import convert_audio_to_wav, get_audio_duration
from pathlib import Path
from call_management import initiate_call, wait_for_call_events, play_audio_file
from conversation import conversation_loop



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
