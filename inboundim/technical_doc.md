# AI Inbound Calling System Documentation

## Overview

This system enables AI-powered voice conversations for inbound calls through FreeSWITCH and AfricasTalking SIP integration. The application answers incoming calls, engages callers in natural conversation using AI, and records the interactions.

### Key Components:

1. **FreeSWITCH Server**: Handles SIP telephony and call routing via AfricasTalking
2. **Socket Server**: Listens for incoming connections from FreeSWITCH
3. **AI Processing Pipeline**:
   - Speech-to-Text (Google Cloud Speech-to-Text)
   - AI Response Generation (Google Gemini)
   - Text-to-Speech (ElevenLabs)
4. **Conversation Management**: Handles the back-and-forth flow of dialogue

## Technical Implementation

### Core Modules

#### Main Server (`main.py`)

Initializes a TCP socket server that listens for incoming connections from FreeSWITCH. Each new connection is handled in a separate thread.

```python
def start_socket_server():
    """
    Start a socket server to listen for inbound calls from FreeSWITCH.
    """
    # Create and configure TCP socket server
    # Accept connections in an infinite loop
    # Spawn a new thread for each connection
```

#### Connection Handler (`connection.py`)

Manages the FreeSWITCH ESL connection for each call:
- Answers the call
- Starts call recording
- Plays initial greeting
- Initiates the conversation loop
- Handles call termination

```python
def handle_connection(client_socket, address):
    """
    Handle an individual FreeSWITCH connection with AI conversation.
    """
    # Establish ESL connection
    # Extract call information (UUID, caller number)
    # Answer call and start recording
    # Play greeting and begin conversation
    # Hang up when conversation ends
```

#### Conversation Management (`conversation.py`)

Orchestrates the AI-powered conversation:
1. Records user speech with silence detection
2. Transcribes speech to text
3. Sends transcription to AI for processing
4. Converts AI response to speech
5. Plays audio response to caller
6. Repeats for multiple turns

```python
def conversation_loop(conn, call_uuid, entire_call_recording_path, max_iterations=5):
    """
    Manage the AI conversation loop with the caller.
    """
    # Initialize conversation history
    # Loop through conversation turns (up to max_iterations)
    # Record user speech, transcribe, generate AI response, play audio
    # Handle errors and termination conditions
    # Play goodbye message and stop recording
```

#### Call Management (`call_management.py`)

Provides utilities for interacting with the active call:
- Checking if call is still active
- Recording user speech with silence detection
- Playing audio files to the caller

```python
def check_call_active(conn, call_uuid):
    """Check if a call is still active."""
    # Use FreeSWITCH API to check call status

def record_user_response(conn, call_uuid):
    """Record caller's voice response with silence detection."""
    # Configure recording with silence detection
    # Monitor for recording events
    # Validate recording file

def play_audio_file(conn, call_uuid, audio_file):
    """Play audio file to the caller with improved reliability."""
    # Verify call is active
    # Convert audio format if needed
    # Play audio and wait for completion
```

#### AI Processing (`ai_processor.py`)

Handles all AI-related functionality:
- Speech transcription using Google Cloud Speech-to-Text
- Generating AI responses with Google Gemini
- Converting text to speech with ElevenLabs

```python
def transcribe_audio(file_path):
    """Transcribe audio file to text using Google Cloud Speech-to-Text."""
    # Initialize Speech-to-Text client
    # Configure and perform transcription
    # Return transcribed text

def process_call_context(call_context, conversation_history=None, system_prompt=None):
    """Process transcribed speech and get an AI-generated response."""
    # Prepare conversation context
    # Generate response from Gemini
    # Return formatted response

def convert_text_to_audio(text, call_uuid):
    """Convert text to spoken audio using ElevenLabs text-to-speech."""
    # Clean and format text
    # Generate speech with ElevenLabs
    # Save audio file and return path
```

#### Audio Processing (`audio_processor.py`)

Utilities for handling audio files:
- Converting between audio formats
- Calculating audio duration
- Downloading audio files from URLs

```python
def convert_audio_to_wav(audio_path):
    """Convert audio file to WAV format compatible with FreeSWITCH."""
    # Use ffmpeg to convert audio formats

def get_audio_duration(file_path):
    """Get the duration of an audio file in seconds."""
    # Use ffprobe to extract audio duration

def download_audio_to_path(audio_url, dest_dir):
    """Download audio from URL to local file system."""
    # Download and save audio file
```

#### Configuration (`config.py`)

Centralizes system configuration:
- Server settings
- API credentials and clients
- Logging configuration
- File paths and directories

## FreeSWITCH Integration

### Dialplan Configuration (`dialplan.example`)

Routes incoming calls from AfricasTalking to the AI system:

```xml
<include>
  <extension name="africastalking">
    <condition field="destination_number" expression="^\+?234\d+$">
      <action application="set" data="domain_name=$${domain}"/>
      <action application="answer"/>
      <action application="sleep" data="1000"/>
      <action application="socket" data="{HOST}:{PORT} async full"/>
      <action application="hangup"/>
    </condition>
  </extension>
</include>
```

### SIP Profile Configuration (`sip_profile.example`)

Configures FreeSWITCH to connect with the AfricasTalking SIP service:

```xml
<include>
  <gateway name="africastalking">
    <param name="register" value="false"/>
    <param name="proxy" value="ng.sip.africastalking.com"/>
    <param name="context" value="public"/>
    <param name="from-user" value="example"/>
    <param name="from-domain" value="ng.sip.africastalking.com"/>
    <param name="realm" value="ng.sip.africastalking.com"/>
    <param name="auth-calls" value="false"/>
    <param name="sip-auth-user" value=""/>
    <param name="sip-auth-password" value=""/>
    <param name="codec-prefs" value="PCMU,PCMA"/>
    <param name="dtmf-type" value="rfc2833"/>
  </gateway>
</include>
```

## Conversation Flow

1. **Call Reception**:
   - FreeSWITCH receives inbound call from AfricasTalking
   - Call is answered
   - Call is routed to the socket application

2. **Call Setup**:
   - Recording begins
   - Greeting is played

3. **Conversation Loop**:
   - User speaks
   - Speech is recorded and transcribed
   - Transcription is sent to Gemini AI
   - AI response is generated
   - Response is converted to speech
   - Speech is played to caller

4. **Call Termination**:
   - Conversation concludes after max iterations
   - Goodbye message is played
   - Call recording is stopped
   - Call is hung up

## Environment Requirements

### Dependencies

- FreeSWITCH with ESL support
- Python 3.8+
- Google Cloud Speech-to-Text
- Google Gemini API
- ElevenLabs API
- FFmpeg for audio processing

### Required Environment Variables

```
SERVER_HOST
SERVER_PORT
GEMINI_API_KEY
FREESWITCH_HOST
FREESWITCH_PORT
FREESWITCH_PASSWORD
ELEVENLABS_API_KEY
ELEVEN_LABS_VOICE_ID
ELEVEN_LABS_MODEL_ID
```


## Deployment Configuration

### Systemd Service Setup

The system is deployed as a systemd service for reliable operation and automatic restart. Create the following service file at `/etc/systemd/system/call-handler.service`:

```ini
[Unit]
Description=AI Inbound Call Handler
After=network.target freeswitch.service

[Service]
User=user
Group=user
WorkingDirectory=/PATH/TO/PROJECT/DIRECTORY
ExecStart=/PATH/TO/VENV/bin/python3 /PATH/TO/PROJECT/DIRECTORY/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Service Management Commands

Control the AI calling system with the following systemd commands:

```bash
# Enable service to start on boot
sudo systemctl enable call-handler.service

# Start the service
sudo systemctl start call-handler.service

# Check service status
sudo systemctl status call-handler.service

# View real-time logs
sudo journalctl -u call-handler.service -f

# Restart the service
sudo systemctl restart call-handler.service

# Stop the service
sudo systemctl stop call-handler.service
```

## Error Handling

The system includes comprehensive error handling for various scenarios:

- Call disconnection detection
- Failed transcription recovery
- AI service interruptions
- Audio conversion and playback issues

Each error case includes appropriate fallback behaviors and logging.

## Limitations

1. Currently supports English language only
2. Maximum 5 conversation turns per call
3. Fixed default voice for text-to-speech
4. Limited error recovery options

## Future Enhancements

1. Multi-language support
2. Dynamic conversation length based on context
3. Improved silence detection parameters
4. Voice customization options
5. Integration with CRM systems for context awareness
6. Fastapi integration for connection to frontend