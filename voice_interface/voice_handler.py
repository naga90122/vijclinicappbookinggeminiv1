# voice_interface/voice_handler.py

from fastapi import FastAPI, WebSocket, Request, Response, APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech_v1beta1 as texttospeech
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx
import base64
import json # For JSON parsing from LLM responses if needed

# Load environment variables from .env file
load_dotenv()

# Set Google Application Credentials if running outside Google Cloud environment
# Ensure your GOOGLE_API_KEY has access to Speech-to-Text and Text-to-Speech APIs
# The API key approach is simpler for demonstration. For production, Google recommends
# service account credentials or workload identity.
# If GOOGLE_APPLICATION_CREDENTIALS is set, it will be preferred.
# Otherwise, we'll try to use the API key in the client initialization if possible (though some Google clients prefer JSON key file)

app = FastAPI(
    title="Voice Interface API",
    description="Handles Speech-to-Text (STT) and Text-to-Speech (TTS) interactions and forwards to Master Agent."
)

# Google Cloud Speech-to-Text and Text-to-Speech clients
# For API Key authentication (less common for official client libraries, usually service account JSON)
# If GOOGLE_API_KEY is preferred for direct API calls, you might need to use `requests` or `httpx`
# directly, not the official client libraries. For this example, we'll assume the client libraries
# can pick up the API key or that a GOOGLE_APPLICATION_CREDENTIALS file is configured.
# If you get authentication errors, consider creating a service account key JSON file
# and setting the GOOGLE_APPLICATION_CREDENTIALS environment variable to its path.
try:
    speech_client = speech.SpeechClient()
    text_to_speech_client = texttospeech.TextToSpeechClient()
    print("[Voice Interface] Google Cloud Speech and Text-to-Speech clients initialized.")
except Exception as e:
    print(f"[Voice Interface] Error initializing Google Cloud clients: {e}")
    print("Ensure GOOGLE_API_KEY is correctly set in .env, or GOOGLE_APPLICATION_CREDENTIALS points to a valid service account key file.")
    speech_client = None
    text_to_speech_client = None

# Master Agent URL
MASTER_AGENT_URL = os.getenv("MASTER_AGENT_URL", "http://master_agent:8000")

# --- Request/Response Models ---
class AudioInput(BaseModel):
    audio_content: str # Base64 encoded audio
    user_id: str

class TextOutput(BaseModel):
    text: str
    user_id: str

class VoiceResponse(BaseModel):
    status: str
    message: str
    audio_content: str = None # Base64 encoded audio response

class MasterAgentMessage(BaseModel):
    user_id: str
    message: str
    is_voice: bool = True


# --- Helper Function for API Calls to Master Agent ---
async def call_master_agent(user_id: str, message: str):
    """Sends transcribed text to the Master Agent."""
    payload = MasterAgentMessage(user_id=user_id, message=message, is_voice=True)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MASTER_AGENT_URL}/process_user_input", json=payload.dict())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error calling Master Agent: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Master Agent error: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error calling Master Agent: {e}")
            raise HTTPException(status_code=503, detail=f"Cannot reach Master Agent service: {e}")

# --- Speech-to-Text Endpoint ---
@app.post("/transcribe", response_model=VoiceResponse)
async def transcribe_audio(audio_input: AudioInput):
    """
    Receives base64 encoded audio, transcribes it using Google STT,
    sends to Master Agent, and returns Master Agent's response as audio.
    """
    if not speech_client or not text_to_speech_client:
        raise HTTPException(status_code=500, detail="Google Cloud clients not initialized.")

    try:
        audio_content_bytes = base64.b64decode(audio_input.audio_content)

        audio = speech.RecognitionAudio(content=audio_content_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, # Or other appropriate encoding
            sample_rate_hertz=16000, # Adjust to your audio's sample rate
            language_code="en-CA", # Canadian English
            # Consider using enhanced models or adaptation for better accuracy
            # model="default", # "default", "phone_call", "video", etc.
            # enable_automatic_punctuation=True,
            # speech_contexts=[{"phrases": ["Dr. Smith", "appointment", "reschedule"]}] # Hints for better recognition
        )

        print(f"[Voice Interface] Transcribing audio for user: {audio_input.user_id}...")
        stt_response = speech_client.recognize(config=config, audio=audio)

        if not stt_response.results:
            return VoiceResponse(status="failure", message="Could not understand audio. Please try again.")

        transcribed_text = stt_response.results[0].alternatives[0].transcript
        print(f"[Voice Interface] Transcribed text: '{transcribed_text}'")

        # Send transcribed text to Master Agent
        master_response = await call_master_agent(audio_input.user_id, transcribed_text)
        response_text = master_response.get("response_text", "I'm sorry, I couldn't get a clear response.")

        # Convert Master Agent's text response to speech
        synthesis_input = texttospeech.SynthesisInput(text=response_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-CA",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE # Or MALE, NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16, # Or MP3, OGG_OPUS
            sample_rate_hertz=16000 # Match desired output sample rate
        )

        print(f"[Voice Interface] Converting text to speech: '{response_text}'")
        tts_response = text_to_speech_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        return VoiceResponse(
            status="success",
            message="Processed and responded with audio.",
            audio_content=base64.b64encode(tts_response.audio_content).decode('utf-8')
        )

    except HTTPException as e:
        return VoiceResponse(status="failure", message=f"Error in Voice Interface: {e.detail}")
    except Exception as e:
        print(f"[Voice Interface] Unexpected error during transcription/TTS: {e}")
        return VoiceResponse(status="failure", message="An unexpected error occurred. Please try again.")

# --- Text-to-Speech Endpoint (for text-based agent responses) ---
@app.post("/synthesize", response_model=VoiceResponse)
async def synthesize_text(text_input: TextOutput):
    """
    Converts text to speech using Google TTS.
    Useful if a text-based agent wants to directly generate audio.
    """
    if not text_to_speech_client:
        raise HTTPException(status_code=500, detail="Google Cloud Text-to-Speech client not initialized.")

    try:
        synthesis_input = texttospeech.SynthesisInput(text=text_input.text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-CA",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16, # Or MP3, OGG_OPUS
            sample_rate_hertz=16000
        )

        tts_response = text_to_speech_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        return VoiceResponse(
            status="success",
            message="Text converted to speech.",
            audio_content=base64.b64encode(tts_response.audio_content).decode('utf-8')
        )
    except Exception as e:
        print(f"[Voice Interface] Unexpected error during TTS: {e}")
        raise HTTPException(status_code=500, detail=f"Text-to-Speech error: {e}")


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint for the agent.
    """
    return {"status": f"{app.title} is healthy"}

