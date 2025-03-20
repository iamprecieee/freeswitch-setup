## System Overview

This system creates a fully automated outbound calling solution that can initiate phone calls, play recorded greetings, capture spoken responses, convert those responses to text, generate contextual replies, convert those replies to natural-sounding speech, and play them back to the caller - all while recording the entire interaction.

## Architecture

The system consists of several interconnected components:

1. **FreeSWITCH Core**: Handles the SIP signaling and media processing for calls
2. **ESL Interface**: Python interface to control FreeSWITCH
3. **Audio Processing**: Handles format conversion and analysis
4. **Recording System**: Captures user responses and full calls
5. **Transcription Engine**: Converts spoken audio to text
6. **Response Generation**: Creates text responses for playback
7. **Text-to-Speech Engine**: Converts responses to spoken audio

These components work together to create a seamless calling experience with natural language processing capabilities.

## Detailed Components

### FreeSWITCH Integration

The script connects to a running FreeSWITCH instance using the Event Socket Library (ESL) interface. This provides a way to control FreeSWITCH programmatically.

```python
conn = ESL.ESLconnection(FREESWITCH_HOST, FREESWITCH_PORT, FREESWITCH_PASSWORD)
if not conn.connected():
    logger.error("Failed to connect to freeswitch")
    exit(1)
```

The ESL connection is maintained throughout the script's execution and is used to send commands and receive events from FreeSWITCH. The script subscribes to all FreeSWITCH events to monitor call progress:

```python
conn.events("plain", "all")
```

This allows the script to track call state transitions, detect when audio playback completes, and monitor recording status.

### Call Initialization

Outbound calls are initiated using FreeSWITCH's originate command. The script supports custom caller ID and uses the "park" extension to maintain call control:

```python
def initiate_call(conn):
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
```

The script initiates the call via a configured SIP gateway (such as Twilio) and returns the unique call UUID assigned by FreeSWITCH, which is used for all subsequent operations on this call.

### Call Event Handling

After initiating a call, the script waits for specific events that indicate the call's progress:

```python
def wait_for_call_events(conn, timeout=5):
    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(500)  # Poll every 0.5 seconds
        if event:
            event_name = event.getHeader("Event-Name")
            if event_name == "CHANNEL_ANSWER":
                return "ANSWERED"
            elif event_name == "CHANNEL_HANGUP":
                return "HANGUP"
```

This function polls for FreeSWITCH events, looking specifically for CHANNEL_ANSWER (indicating the call was picked up) or CHANNEL_HANGUP (indicating the call was rejected or failed). The timeout parameter controls how long to wait before giving up.

Similarly, the script monitors playback completion using events:

```python
def wait_for_playback_completion(conn, call_uuid, timeout=30):
    while time.time() - start_time < timeout:
        event = conn.recvEventTimed(1000)
        if event:
            event_name = event.getHeader("Event-Name")
            if event_name == "PLAYBACK_STOP":
                return True
```

This ensures that audio files are fully played before proceeding to the next action.

### Audio Management

The script handles various audio processing tasks:

#### Audio Format Conversion

FreeSWITCH works best with specific WAV format files, so the script converts other formats using ffmpeg:

```python
def convert_audio_to_wav(audio_path):
    wav_path = audio_path.with_suffix(".wav")
    subprocess.call([
        "ffmpeg", "-i", str(audio_path),
        "-ar", "8000", "-ac", "1",
        "-f", "wav", str(wav_path), "-y"
    ])
```

This creates 8kHz mono WAV files, which are optimal for telephone audio quality.

#### Audio Duration Detection

To accurately time playback and recording operations, the script determines audio file durations:

```python
def get_audio_duration(file_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
         "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    duration = float(result.stdout.strip())
```

This information is used to calculate appropriate wait times after playing audio files.

#### Audio Playback

The script can play audio files to the caller using FreeSWITCH's uuid_broadcast command:

```python
def play_audio_file(conn, call_uuid, audio_file):
    # Handle URL downloads if needed
    play_cmd = f"uuid_broadcast {call_uuid} {audio_file} aleg"
    conn.api(play_cmd)
```

The function supports both local files and remote URLs. For URLs, it first downloads the audio and converts it to the proper format before playback.

### Recording System

The recording system captures caller responses for processing:

```python
def record_user_response(conn, call_uuid):
    recording_filename = f"client_response_{call_uuid}.wav"
    recording_path = RECORDINGS_DIR / recording_filename
    
    record_cmd = f"uuid_record {call_uuid} start {recording_path} 20000 30 3000"
    conn.api(record_cmd)
```

The recording parameters are:
- Maximum recording length: 20 seconds (20000 ms)
- Silence threshold: 30 (lower values are more sensitive)
- Silence duration: 3 seconds (3000 ms)

The script monitors for recording-related events:
- RECORD_START: Indicates recording has begun
- RECORD_STOP: Indicates recording has ended (usually due to silence detection)

If no RECORD_STOP event is received within the timeout period, the script manually stops the recording:

```python
stop_cmd = f"uuid_record {call_uuid} stop {recording_path}"
conn.api(stop_cmd)
```

The script also records the entire call for later reference:

```python
call_record_cmd = f"uuid_record {call_uuid} start {call_recording_path}"
conn.api(call_record_cmd)
```

### Transcription Engine

The transcription engine uses ElevenLabs API to convert speech to text:

```python
def transcribe_audio(file_path: str) -> str:
    with open(file_path, "rb") as audio_file:
        audio_data = BytesIO(audio_file.read())

    transcription = client.speech_to_text.convert(
        file=audio_data,
        model_id="scribe_v1",
    )
    return transcription.text
```

This function reads the recorded audio file, sends it to the ElevenLabs API, and returns the transcribed text. The ElevenLabs "scribe_v1" model provides high-quality speech recognition suitable for telephone audio.

### Response Generation

After transcribing the caller's response, the script generates a reply using the Gooey AI text-to-speech API:

```python
def convert_text_to_audio(text):
    text = re.sub(r'\([^)]*\)', '', text)
    formatted_text = re.sub(r'\s+', ' ', text).strip()

    payload = {
        "text_prompt": f"{formatted_text}",
        "azure_voice_name": "en-NG-AbeoNeural",
    }
    
    response = requests.post(
        "https://api.gooey.ai/v2/TextToSpeech",
        headers={"Authorization": "bearer " + GOOEY_API_KEY},
        json=payload,
    )
    
    result = response.json()["output"]["audio_url"]
    return result
```

This function:
1. Cleans up the transcribed text (removes parentheses, normalizes spacing)
2. Sends the text to Gooey AI for conversion to speech
3. Specifies "en-NG-AbeoNeural" voice for Nigerian-accented English
4. Returns a URL to the generated audio file

### Conversation Loop

The heart of the script is the conversation loop, which ties all components together:

```python
def conversation_loop(conn, call_uuid, entire_call_recording_path, max_iterations=5):
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        
        # Check if call is still active
        if not check_call_active(conn, call_uuid):
            break
            
        # Record user response
        recorded_response = record_user_response(conn, call_uuid)
        
        # Check if valid recording
        if not recorded_response:
            break
        
        # Transcribe and process
        transcription = transcribe_audio(recorded_response)
        
        # Generate and play response
        audio_response = convert_text_to_audio(transcription)
        play_audio_file(conn, call_uuid, audio_response)
```

This function:
1. Runs for a configurable number of iterations
2. Checks call status before each step
3. Records the caller's response
4. Transcribes the response
5. Generates an appropriate audio reply
6. Plays the reply back to the caller
7. Repeats until the maximum iterations are reached or the call ends

## Setup and Installation

### Prerequisites

Before using this script, you'll need:

- A server with FreeSWITCH installed and configured
- Python 3.8 or higher
- FreeSWITCH Event Socket Library (ESL) for Python
- ffmpeg and ffprobe utilities
- ElevenLabs API account for speech recognition
- Gooey AI API account for text-to-speech
- A SIP provider account (such as Twilio) for outbound calling

### Environment Setup

1. Install required Python packages:

```bash
pip install python-esl requests python-dotenv elevenlabs numpy
```

2. Install system dependencies:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

3. Create a `.env` file with your configuration:

```
FREESWITCH_HOST=127.0.0.1
FREESWITCH_PORT=8021
FREESWITCH_PASSWORD=ClueCon

CALLER_ID=+1234567890
GATEWAY=twilio
PHONE_NUMBER=+1234567890

ELEVENLABS_API_KEY=your_elevenlabs_api_key
GOOEY_API_KEY=your_gooey_api_key
```

### FreeSWITCH Configuration

Refer to [freeswitch-setup-guide](https://github.com/iamprecieee/freeswitch-setup/blob/main/README.md)

### API Keys

1. **ElevenLabs**: Sign up at [elevenlabs.io](https://elevenlabs.io), obtain an API key from your profile settings.

2. **Gooey AI**: Register at [gooey.ai](https://gooey.ai) and get your API key from the dashboard.

## Usage Guide

### Basic Usage

The script execution flow:

1. Connects to FreeSWITCH
2. Initiates a call to the configured number
3. Waits for the call to be answered
4. Records the entire call
5. Plays the greeting audio
6. Enters the conversation loop:
   - Records the caller's response
   - Transcribes the response
   - Generates a reply
   - Plays the reply
7. After the configured number of iterations (or if the call ends):
   - Stops all recordings
   - Hangs up the call

### Call Flow Sequence

The detailed call flow sequence is:

1. **Initialization**:
   - Load environment variables
   - Connect to FreeSWITCH
   - Prepare audio files

2. **Call Setup**:
   - Send originate command to FreeSWITCH
   - Obtain call UUID
   - Wait for call events (answer/hangup)

3. **Call Handling**:
   - Start recording the entire call
   - Play initial greeting
   - Wait for playback completion

4. **Conversation Loop**:
   - Record user response (with silence detection)
   - Check recording validity
   - Transcribe audio to text
   - Clean and format transcribed text
   - Convert text to audio via Gooey AI
   - Play generated audio response
   - Repeat for configured iterations

5. **Call Teardown**:
   - Stop all recordings
   - Hang up the call
   - Clean up resources

### Customization Options

The script includes several parameters that can be customized:

- **Max Iterations**: Change `max_iterations` in the `conversation_loop` function call
- **Recording Parameters**: Modify silence thresholds and timeouts in `record_user_response`
- **Timeout Values**: Adjust wait times for call events and playback completion
- **Voice Options**: Change the `azure_voice_name` parameter in `convert_text_to_audio`

## Debugging and Logging

The script uses Python's logging module with DEBUG level enabled, providing detailed information about:

- ESL connection status
- Call initiation and progress
- Event processing
- Audio file operations
- Recording status
- API interactions
- Error conditions

Example log output:

```
2025-03-20 12:04:23,758 - INFO - Starting freeswitch call script
2025-03-20 12:04:23,758 - INFO - Connecting to freeswitch at 127.0.0.1:8021
2025-03-20 12:04:23,764 - INFO - Successfully connected to FreeSWITCH
2025-03-20 12:04:23,764 - INFO - Initiating call with command: originate {...}
2025-03-20 12:04:55,925 - INFO - Call initiated successfully
2025-03-20 12:04:55,925 - INFO - +OK 86d5942c-a452-4a96-aebf-d68bf2e80b39
2025-03-20 12:04:55,925 - INFO - Call initiated with UUID: 86d5942c-a452-4a96-aebf-d68bf2e80b39
```

For troubleshooting specific issues:

- **Call Rejection**: Check Twilio console for IP access restrictions
- **Recording Failures**: Verify FreeSWITCH permissions on recording directory
- **API Failures**: Check API key validity and rate limits
- **Audio Issues**: Test audio files directly with FreeSWITCH console


## Technical Reference

### FreeSWITCH ESL Commands

The script uses these primary FreeSWITCH commands:

- `originate`: Initiates outbound calls
- `uuid_broadcast`: Plays audio to a call
- `uuid_record`: Records audio from a call
- `uuid_exists`: Checks if a call is still active
- `uuid_kill`: Terminates a call

### Audio Parameters

- Sample Rate: 8000 Hz (telephone quality)
- Channels: 1 (mono)
- Format: WAV (uncompressed)
- Bit Depth: 16-bit

### Silence Detection Parameters

- Silence Threshold: 30 (sensitivity level, lower = more sensitive)
- Silence Duration: 3000 ms (how long silence must persist to trigger stop)
- Maximum Recording Duration: 20000 ms

### API Specifications

- **ElevenLabs Transcription**:
  - Model: scribe_v1
  - Input: Audio file (WAV format)
  - Output: Transcribed text

- **Gooey AI Text-to-Speech**:
  - Voice: en-NG-AbeoNeural (Nigerian English)
  - Input: Text string
  - Output: Audio URL
