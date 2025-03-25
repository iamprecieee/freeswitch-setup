# =====================================================================
# Main Conversation Logic
# =====================================================================

from config import ESL, logger
from call_management import check_call_active, record_user_response, play_audio_file
from ai_processor import transcribe_audio, process_call_context, convert_text_to_audio
from pathlib import Path
import time


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