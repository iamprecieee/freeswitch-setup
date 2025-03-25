
# =====================================================================
# Configuration and Setup
# =====================================================================

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