# =====================================================================
# Inbound Call connection Handler
# =====================================================================

from config import logger, ESL, INITIAL_GREETING, OUTPUT_DIR
import time
from call_management import play_audio_file
from conversation import conversation_loop


def handle_connection(client_socket, address):
    """
    Handle an individual FreeSWITCH connection with AI conversation.
    """
    logger.info(f"New connection from {address}")
    
    try:
        # Create an ESL Connection using the socket's file descriptor
        socket_fd = client_socket.fileno()
        conn = ESL.ESLconnection(socket_fd)
        
        if not conn.connected():
            logger.error("ESL connection failed")
            return
        
        conn.events("plain", "RECORD_START RECORD_STOP CHANNEL_ANSWER CHANNEL_HANGUP")
        
        # Get call information
        info = conn.getInfo()
        if info:
            call_uuid = info.getHeader("Unique-ID")
            caller_number = info.getHeader("Caller-Caller-ID-Number")
            logger.info(f"Call from {caller_number} with UUID: {call_uuid}")
            
            # Answer the call
            conn.execute("answer")
            logger.info("Call answered")
            
            recording_path = OUTPUT_DIR/f"entire_output_{call_uuid}.wav"
            
            # Start recording the entire call
            start_entire_cmd = f"uuid_record {call_uuid} start {recording_path}"
            conn.api(start_entire_cmd)
            logger.info(f"Started recording entire call: {recording_path}")
            
            time.sleep(0.5)
            
            # Play the greeting
            play_audio_file(conn, call_uuid, INITIAL_GREETING)
            conversation_loop(conn, call_uuid, recording_path, 5)
            
            conn.execute("hangup")
            logger.info("Call hung up")
        else:
            logger.warning("Could not get call information")
            
    except Exception as e:
        logger.error(f"Error handling connection: {e}")
    finally:
        logger.info("Connection handling complete")