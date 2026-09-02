"""
Text-to-Speech service using ElevenLabs.
Takes text and produces an audio file the AI can "speak" on a call.
"""
import os
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# A default pre-made ElevenLabs voice (neutral, not cloned). You can swap
# this voice_id for any other base voice from your ElevenLabs dashboard.
DEFAULT_VOICE_ID = "CwhRBWXzGAHq8TQ4Fs17"  # "Rachel" - default ElevenLabs voice


def synthesize_speech(text: str, output_path: str, voice_id: str = DEFAULT_VOICE_ID) -> str:
    """
    Convert text to speech and save it as an audio file.

    Args:
        text: the text to speak
        output_path: where to save the generated audio (e.g. "output.mp3")
        voice_id: which ElevenLabs voice to use

    Returns:
        The output_path, for convenience.
    """
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        text=text,
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)

    return output_path
