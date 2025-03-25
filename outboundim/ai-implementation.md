# AI-Enhanced Calling System

## System Overview

This system extends the original outbound calling solution with advanced AI capabilities, creating a fully autonomous conversational agent that can initiate calls, understand spoken responses, generate contextually relevant replies, and maintain meaningful conversations - all while providing natural-sounding voice interactions.

## Architecture

The enhanced system builds on the original FreeSWITCH foundation while adding several AI-powered components:

1. **FreeSWITCH Core**: Handles the SIP signaling and media processing for calls
2. **ESL Interface**: Python interface to control FreeSWITCH
3. **Audio Processing**: Handles format conversion and analysis
4. **Recording System**: Captures user responses and full calls
5. **Advanced Transcription**: Google Cloud Speech-to-Text for accurate speech recognition
6. **AI Response Generation**: Google Gemini for contextually aware conversation management
7. **Premium TTS**: ElevenLabs for high-quality, natural-sounding speech synthesis
8. **Conversation Management**: Maintains dialogue history for contextual understanding

These components work together to create a seamless, AI-driven calling experience with significantly improved natural language understanding and generation capabilities.

## Detailed Components

### FreeSWITCH Integration

The script connects to a running FreeSWITCH instance using the Event Socket Library (ESL) interface, identical to the original implementation:

```python
conn = ESL.ESLconnection(FREESWITCH_HOST, FREESWITCH_PORT, FREESWITCH_PASSWORD)
if not conn.connected():
    logger.error("Failed to connect to freeswitch")
    exit(1)
```

The ESL connection handling, call initialization, audio management, and recording systems remain largely unchanged from the original implementation, providing a stable foundation for the AI enhancements.

### Google Cloud Speech-to-Text Integration

The system uses Google Cloud Speech-to-Text for improved transcription accuracy, particularly for phone-quality audio:

```python
def transcribe_audio(file_path: str) -> str:
    """Transcribes an audio file using Google Cloud Speech-to-Text API."""
    try:
        client = speech.SpeechClient()
        
        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()
            audio = speech.RecognitionAudio(content=audio_data)
            
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code='en-US'
        )
        
        response = client.recognize(config=config, audio=audio)

        transcript = response.results[0].alternatives[0].transcript
        print(transcript)
        
        return transcript

    except Exception as e:
        print(f"Error during transcription: {e}")
        return ""
```

This implementation offers several advantages over the original:

- Better handling of telephone-quality audio
- Improved accuracy for different accents and speech patterns
- Superior noise filtering capabilities
- Enhanced punctuation and formatting

The transcription configuration uses LINEAR16 encoding (standard for WAV files) and US English as the default language, but these parameters can be adjusted for other languages or audio formats.

### ElevenLabs Text-to-Speech

For voice generation, the system uses ElevenLabs' high-quality text-to-speech API:

```python
def convert_text_to_audio(text, call_uuid):
    """Takes in transcribed audio text and returns a local file path to the audio."""
    text = re.sub(r'\([^)]*\)', '', text)
    formatted_text = re.sub(r'\s+', ' ', text).strip()
    
    audio = client.text_to_speech.convert(
        voice_id="JBFqnCBsd6RMkjVDRZzb", # Adam pre-made voice
        output_format="mp3_44100_128",
        text=formatted_text,
        model_id="eleven_flash_v2_5", # use the turbo model for low latency
    )
    
    with open(f"/tmp/freeswitch_recordings/output_{call_uuid}.wav", "wb") as out:
        for chunk in audio:
            if chunk:
                out.write(chunk)
    
    return f"/tmp/freeswitch_recordings/output_{call_uuid}.wav"
```

This implementation provides:
- Access to studio-quality voices with natural prosody and intonation
- Low-latency generation using the "Flash" model variant
- Consistent voice identity throughout the conversation
- Higher audio quality for better caller experience

The function performs text cleaning (removing parenthetical content and normalizing spacing) before generating audio, ensuring optimal speech output.

### Google Gemini AI Integration

The core of the enhanced system is the integration with Google's Gemini AI for natural language understanding and response generation:

```python
def send_message_to_gemini(
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    model: str = "gemini-1.5-pro-latest"
) -> str:
    """
    Send messages to Google Gemini AI and get a response.
    """
    # Default system prompt
    default_system_prompt = """
    You are an enthusiastic, engaging, and friendly AI guide. Your responses should be warm, 
    concise, and natural — like a helpful friend! Keep the conversation fun and approachable. Do not use emojis and make your
    response seem non-ai generated.
    """

    final_system_prompt = f"{default_system_prompt}\n\n{system_prompt}" if system_prompt else default_system_prompt

    # Convert messages to Gemini's expected format
    message_texts = [msg["content"] for msg in messages]

    try:
        # Create the model
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            [final_system_prompt] + message_texts)

        return response.text.strip()

    except Exception as e:
        print(f"Error calling Google Gemini API: {str(e)}")
        return "I'm sorry, I'm having trouble processing your request right now. Please try again later."
```

This function:
1. Takes a list of conversation messages in a standard format
2. Applies a system prompt that defines the AI's persona and behavior
3. Converts the messages to Gemini's expected format
4. Makes the API call to Gemini's latest model
5. Returns the generated response text

The system prompt is particularly important as it shapes the conversational style and capabilities of the AI agent.

### Conversation Management

A key enhancement is the addition of conversation memory, allowing the system to maintain context across multiple exchanges:

```python
def conversation_loop(conn, call_uuid, entire_call_recording_path, max_iterations=5):
    """
    Continuously record the user's response, process it with Gemini AI, and play the AI response.
    The loop continues until a maximum number of iterations is reached or
    no meaningful response is recorded.
    """

    iteration = 0
    conversation_history = []  # Stores messages to maintain chat context

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"\n--- Conversation iteration {iteration} ---")
        
        # Record and process user response...
        
        # Maintain conversation history
        conversation_history.append({"role": "user", "content": transcription})

        # Get AI response
        ai_response = process_call_context(
            call_context=transcription, 
            conversation_history=conversation_history
        )
        
        # Store AI response in conversation history
        conversation_history.append({"role": "assistant", "content": ai_response})

        # Convert and play response...
```

The `conversation_history` list maintains the full dialogue context, enabling the AI to:
- Remember previous user statements
- Provide contextually relevant responses
- Reference earlier parts of the conversation
- Build a coherent conversation flow

### Response Processing

The system uses a dedicated function to process call context and generate appropriate responses:

```python
def process_call_context(
    call_context: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    Process call context and get an appropriate response from Gemini AI.
    """
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + \
        [{"role": "user", "content": call_context}]

    response = send_message_to_gemini(
        messages=messages,
        system_prompt=system_prompt
    )

    return response
```

This function:
1. Takes the current context and conversation history
2. Formats them for the Gemini API
3. Optionally applies a custom system prompt
4. Returns the generated response

## Setup and Installation

### Prerequisites

Before using this enhanced script, you'll need:

- A server with FreeSWITCH installed and configured
- Python 3.8 or higher
- FreeSWITCH Event Socket Library (ESL) for Python
- ffmpeg and ffprobe utilities
- Google Cloud Platform account with Speech-to-Text API enabled
- Google AI Studio account with Gemini Pro API access
- ElevenLabs API account for high-quality TTS
- A SIP provider account (such as Twilio) for outbound calling

### Environment Setup

1. Install required Python packages:

```bash
pip install python-esl requests python-dotenv elevenlabs google-cloud-speech google-generativeai
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
GEMINI_API_KEY=your_gemini_api_key

# Path to Google Cloud credentials file
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/credentials.json
```

4. Set up Google Cloud credentials:
   - Create a service account in the Google Cloud Console
   - Download the JSON credentials file
   - Set the path in the `.env` file

### API Keys

1. **ElevenLabs**: Sign up at [elevenlabs.io](https://elevenlabs.io) and obtain an API key from your profile settings.

2. **Google Gemini**: Visit [AI Studio](https://aistudio.google.com) to create an API key. Ensure you have access to the Gemini Pro model.

3. **Google Cloud**: Create a project in the Google Cloud Console, enable the Speech-to-Text API, create a service account, and download credentials.

## Usage Guide

### Basic Usage

The script execution flow:

1. Connects to FreeSWITCH
2. Initiates a call to the configured number
3. Waits for the call to be answered
4. Records the entire call
5. Plays the greeting audio
6. Enters the AI conversation loop:
   - Records the caller's response
   - Transcribes the response using Google Cloud
   - Passes the transcription to Gemini AI with conversation history
   - Generates a contextually relevant reply
   - Converts the reply to speech using ElevenLabs
   - Plays the response to the caller
7. After the configured number of iterations (or if the call ends):
   - Stops all recordings
   - Hangs up the call

### Call Flow Sequence

The detailed AI call flow sequence is:

1. **Initialization**:
   - Load environment variables and configure API clients
   - Connect to FreeSWITCH
   - Initialize Gemini AI and Google Cloud clients

2. **Call Setup**:
   - Send originate command to FreeSWITCH
   - Obtain call UUID
   - Wait for call events (answer/hangup)

3. **Call Handling**:
   - Start recording the entire call
   - Play initial greeting
   - Initialize empty conversation history

4. **AI Conversation Loop**:
   - Record user response (with silence detection)
   - Transcribe audio to text using Google Cloud Speech-to-Text
   - Add user message to conversation history
   - Process context with Gemini AI considering full conversation history
   - Add AI response to conversation history
   - Convert AI text to speech via ElevenLabs
   - Play generated audio response
   - Repeat for configured iterations

5. **Call Teardown**:
   - Stop all recordings
   - Hang up the call
   - Clean up resources

### Customization Options

The AI implementation includes several customizable parameters:

- **AI Persona**: Modify the `default_system_prompt` in the `send_message_to_gemini` function
- **Voice Selection**: Change the `voice_id` parameter in `convert_text_to_audio`
- **Model Selection**: Adjust the Gemini model variant in `send_message_to_gemini`
- **Language Settings**: Update the `language_code` parameter in the Speech-to-Text configuration
- **TTS Quality**: Modify the `model_id` and `output_format` in the ElevenLabs API call

## Technical Reference

### Google Cloud Speech-to-Text Parameters

The system uses these primary Speech-to-Text settings:

- Encoding: LINEAR16 (standard for WAV files)
- Language: en-US (US English)
- Sample Rate: 8000 Hz (telephone quality)
- Channels: 1 (mono)

For optimal results with phone calls, consider these additional configuration options:

```python
config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    language_code='en-US',
    sample_rate_hertz=8000,
    audio_channel_count=1,
    enable_automatic_punctuation=True,
    use_enhanced=True,
    model='phone_call'
)
```

### ElevenLabs Voice Settings

The system uses these ElevenLabs parameters:

- Voice: "Adam" (voice_id="JBFqnCBsd6RMkjVDRZzb")
- Model: eleven_flash_v2_5 (low-latency variant)
- Output Format: mp3_44100_128 (high-quality MP3)

For different voice characteristics, you can adjust these parameters:

```python
# Voice settings for more control over speech characteristics
voice_settings=VoiceSettings(
    stability=0.5,       # 0.0-1.0: Higher values make voice more consistent
    similarity_boost=0.8, # 0.0-1.0: Higher values ensure voice stays on-character
    style=0.0,           # 0.0-1.0: Higher values add more expressiveness
    use_speaker_boost=True, # Enhances clarity for standard speakers
    speed=1.0,           # Adjust speech rate (0.5-2.0)
)
```

### Gemini AI Parameters

The system uses these Gemini API settings:

- Model: gemini-1.5-pro-latest (latest pro version)
- System Prompt: Defines conversational style and behaviors
- Message Format: List of role/content dictionaries

For different conversation styles, modify the system prompt:

```python
# Example system prompts for different use cases
sales_prompt = """
You are a friendly sales representative for a technology company.
Focus on understanding customer needs, addressing objections politely,
and guiding the conversation toward closing opportunities. Speak naturally
and avoid sounding scripted. Don't be pushy but do try to move the 
conversation forward.
"""

support_prompt = """
You are a patient, helpful technical support agent. Listen carefully to 
customer issues, ask clarifying questions when needed, and provide 
step-by-step solutions. Show empathy for frustrations while maintaining
a professional tone. Focus on resolving the immediate issue before
suggesting additional resources.
"""
```

### Performance Considerations

- **Latency**: The entire AI processing loop (transcription, generation, TTS) typically takes 2-4 seconds
- **Memory Usage**: Conversation history grows with each exchange, but remains manageable for typical call durations
- **API Costs**: Usage of three separate AI services (Google Speech, Gemini, ElevenLabs) incurs separate billing
- **Call Duration**: The system is optimized for conversations of 3-5 exchanges but can be extended
