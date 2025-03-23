# =====================================================================
# Main Script Initialization
# =====================================================================

from config import logger, SERVER_HOST, SERVER_PORT
import socket
import time
import threading
from connection import handle_connection     
    

def start_socket_server():
    """
    Start a socket server to listen for inbound calls from FreeSWITCH.
    """
    try:
        # Create TCP socket server
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((SERVER_HOST, SERVER_PORT))
        server_socket.listen(5)
        
        logger.info(f"Socket server listening on {SERVER_HOST}:{SERVER_PORT}")
        
        # Main loop to accept connections
        while True:
            try:
                client_socket, address = server_socket.accept()
                logger.info(f"Accepted connection from {address}")
                
                # Handle connection in a new thread
                thread = threading.Thread(
                    target=handle_connection,
                    args=(client_socket, address)
                )
                thread.daemon = True
                thread.start()
                
            except Exception as e:
                logger.error(f"Error accepting connection: {e}")
                time.sleep(1)
                
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        server_socket.close()


if __name__ == "__main__":
    logger.info("Starting AI inbound call handler...")
    start_socket_server()