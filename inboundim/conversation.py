# =====================================================================
# Main Conversation Logic
# =====================================================================

from config import logger, ESL
from pathlib import Path
from call_management import check_call_active, record_user_response, play_audio_file
from ai_processor import transcribe_audio, convert_text_to_audio, process_call_context
import time


def conversation_loop(
    conn: ESL.ESLconnection,
    call_uuid: str,
    entire_call_recording_path: Path,
    max_iterations: int = 5,
) -> None:
    """
    Manage the AI conversation loop with the caller.

    Records user speech, processes it with AI, generates responses,
    and plays them back to create a natural conversation flow.
    """
    iteration = 0
    conversation_history = []  # Tracks conversation for context

    # First ensure the call is still active
    if not check_call_active(conn, call_uuid):
        logger.error("Call no longer active at conversation start")
        return
    
    # Add a brief pause before starting - helps stabilize the connection
    time.sleep(0.5)
    
    if check_call_active(conn, call_uuid):
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

            if not transcription:
                # Play a prompt asking the caller to speak again
                retry_prompt = "I'm sorry, I couldn't hear you. Could you please try again?"
                retry_audio = convert_text_to_audio(
                    retry_prompt, f"retry_{call_uuid}_{iteration}"
                )
                play_audio_file(conn, call_uuid, retry_audio)
                continue

            # Step 3: Update conversation history
            conversation_history.append({"role": "user", "content": transcription})

            # Step 4: Generate AI response
            logger.info("Processing with Gemini AI...")
            try:
                ai_response = process_call_context(
                    call_context=transcription, conversation_history=conversation_history
                )
            except Exception as e:
                logger.warning(f"Failed to get AI response: {str(e)}")
                error_msg = "I'm sorry, I'm having trouble understanding. Could you please try again?"
                error_audio = convert_text_to_audio(
                    error_msg, f"error_{call_uuid}_{iteration}"
                )
                play_audio_file(conn, call_uuid, error_audio)
                continue

            logger.info(f"AI Response: {ai_response}")

            # Step 5: Update conversation history with AI response
            conversation_history.append({"role": "assistant", "content": ai_response})

            # Step 6: Convert response to speech
            logger.info("Converting AI response to audio...")
            try:
                audio_response = convert_text_to_audio(
                    ai_response, f"{call_uuid}_{iteration}"
                )
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

        # Play goodbye message
        if check_call_active(conn, call_uuid):
            goodbye_msg = "Thank you for calling. Have a great day!"
            goodbye_audio = convert_text_to_audio(goodbye_msg, f"goodbye_{call_uuid}")
            play_audio_file(conn, call_uuid, goodbye_audio)

        # Conversation loop complete
        logger.info("Conversation loop ended after %d iterations", iteration)

        # Stop recording the entire call
        stop_entire_cmd = f"uuid_record {call_uuid} stop {entire_call_recording_path}"
        conn.api(stop_entire_cmd)
        logger.info(f"Stopped recording entire call: {entire_call_recording_path}")

    # Ensure the call is properly hung up
    if check_call_active(conn, call_uuid):
        time.sleep(0.5)  # Brief pause before hangup
        return