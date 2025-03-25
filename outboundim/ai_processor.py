# =====================================================================
# AI Speech and Language Processing Functions
# =====================================================================

from google.cloud import speech
from config import logger, genai, eleven_labs_client
from typing import Dict, List, Optional, Tuple, Union
import re


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio file to text using Google Cloud Speech-to-Text.
    
    Args:
        file_path: Path to the audio file to transcribe
        
    Returns:
        Transcribed text or empty string if transcription failed
    """
    try:
        speech_client = speech.SpeechClient()
        
        # Read the audio file
        with open(file_path, "rb") as audio_file:
            audio_data = audio_file.read()
            audio = speech.RecognitionAudio(content=audio_data)
            
        # Configure the recognition request
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code='en-US'
        )
        
        # Perform the transcription
        response = speech_client.recognize(config=config, audio=audio)

        # Extract the transcript from the response
        transcript = response.results[0].alternatives[0].transcript
        logger.info(f"Transcript: {transcript}")
        
        return transcript

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return ""


def process_call_context(
    call_context: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    Process transcribed speech and get an AI-generated response.
    
    Args:
        call_context: Current transcribed user message
        conversation_history: Previous messages for context
        system_prompt: Custom instructions for the AI
        
    Returns:
        Generated AI response text
    """
    # Initialize empty history if none provided
    if conversation_history is None:
        conversation_history = []

    # Add current message to conversation context
    messages = conversation_history + [{"role": "user", "content": call_context}]
    
    # Generate response using Gemini
    response = send_message_to_gemini(
        messages=messages, 
        system_prompt=system_prompt
    )

    return response


def send_message_to_gemini(
    messages: List[Dict[str, str]],
    system_prompt: Optional[str] = None,
    model: str = "gemini-1.5-pro-latest"
) -> str:
    """
    Send conversation to Google Gemini AI and get a response.
    
    Args:
        messages: List of conversation messages with 'role' and 'content'
        system_prompt: Custom behavior instructions for the AI
        model: Gemini model identifier to use
        
    Returns:
        Generated AI response text
    """
    # Default personality and behavior instructions
    default_system_prompt = """
    You are an enthusiastic, engaging, and friendly AI guide. Your responses should be warm, 
    concise, and natural — like a helpful friend! Keep the conversation fun and approachable. 
    Do not use emojis and make your response seem non-ai generated.
    """

    # Combine default with custom instructions if provided
    final_system_prompt = (
        f"{default_system_prompt}\n\n{system_prompt}" 
        if system_prompt else default_system_prompt
    )

    # Convert messages to Gemini's format (list of text parts)
    message_texts = [msg["content"] for msg in messages]

    try:
        # Initialize model and generate response
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            [final_system_prompt] + message_texts
        )

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error calling Google Gemini API: {str(e)}")
        return "I'm sorry, I didn't quite catch that."


def convert_text_to_audio(text: str, call_uuid: str) -> str:
    """
    Convert text to spoken audio using ElevenLabs text-to-speech.
    
    Args:
        text: Text to convert to speech
        call_uuid: Call UUID for filename reference
        
    Returns:
        Path to the generated audio file
    """
    # Clean and normalize the text
    text = re.sub(r'\([^)]*\)', '', text)  # Remove text in parentheses
    formatted_text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    
    # Generate speech using ElevenLabs
    audio = eleven_labs_client.text_to_speech.convert(
        voice_id="RAVWJW17BPoSIf05iXxf",  # Voice identifier
        output_format="mp3_44100_128",    # High-quality audio format
        text=formatted_text,
        model_id="eleven_flash_v2_5",     # Optimized for low latency
    )
    
    # Save the audio to a file
    output_path = f"/tmp/freeswitch_recordings/output_{call_uuid}.wav"
    with open(output_path, "wb") as out:
        for chunk in audio:
            if chunk:
                out.write(chunk)
    
    logger.info(f'Audio content written to file "{output_path}"')
    return output_path