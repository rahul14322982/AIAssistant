"""
Speech-to-Text service using Deepgram.
Takes an audio file and returns the transcribed text.

Deepgram's "phonecall" model is tuned specifically for phone-call audio,
which fits this use case better than a general-purpose model.
"""
import os
from deepgram import DeepgramClient

client = DeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file to text using Deepgram.

    Args:
        file_path: path to an audio file (mp3, wav, m4a, etc.)

    Returns:
        The transcribed text.
    """
    with open(file_path, "rb") as audio_file:
        buffer_data = audio_file.read()

    response = client.listen.v1.media.transcribe_file(
        request=buffer_data,
        model="nova-2-phonecall",  # tuned for phone-call audio
        smart_format=True,
        punctuate=True,
    )

    transcript = response.results.channels[0].alternatives[0].transcript
    return transcript
