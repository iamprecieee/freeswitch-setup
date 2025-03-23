# =====================================================================
# Configuration and Setup
# =====================================================================

import logging
import os
from pathlib import Path

# Third-party dependencies
import ESL
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from google import generativeai as genai


BASE_DIR = Path(__file__).resolve().parent

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("freeswitch_inbound_ai")

# Load environment variables
load_dotenv(f"{BASE_DIR}/.env")

# Socket server settings
SERVER_HOST = os.getenv("SERVER_HOST")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

# Set up API credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f"{BASE_DIR}/.google-cred.json"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# FreeSWITCH connection settings
FREESWITCH_HOST = os.getenv("FREESWITCH_HOST", "127.0.0.1")
FREESWITCH_PORT = int(os.getenv("FREESWITCH_PORT", "8021"))
FREESWITCH_PASSWORD = os.getenv("FREESWITCH_PASSWORD", "ClueCon")

# Audio paths and settings
INITIAL_GREETING = Path(os.getenv("INITIAL_GREETING", "/tmp/freeswitch/welcome.wav"))
RECORDINGS_DIR = Path("/tmp/freeswitch/recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = Path("/tmp/freeswitch/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Initialize API clients
eleven_labs_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Elevenlabs voice settings
ELEVEN_LABS_VOICE_ID = os.getenv("ELEVEN_LABS_VOICE_ID")
ELEVEN_LABS_MODEL_ID = os.getenv("ELEVEN_LABS_MODEL_ID")