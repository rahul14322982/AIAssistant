"""
Telephony service using Twilio.
Places outbound calls and plays a generated message to whoever answers.
"""
import os
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# This must be a PUBLIC url (via ngrok during local dev) so Twilio's
# servers can reach your backend to fetch the TwiML instructions and audio.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def place_outbound_call(to_number: str, audio_filename: str) -> str:
    """
    Place an outbound call and have Twilio play the generated message audio.

    Args:
        to_number: recipient's phone number, in E.164 format (e.g. +919876543210)
        audio_filename: the filename (not full path) of the generated mp3,
                         e.g. "3f2a91bc-xxxx_message.mp3" — same name returned
                         by /generate-outbound-message

    Returns:
        The Twilio Call SID (useful for checking call status later).
    """
    if not PUBLIC_BASE_URL:
        raise RuntimeError(
            "PUBLIC_BASE_URL is not set in .env — this must be your ngrok "
            "https URL so Twilio can reach your local server."
        )

    twiml_url = f"{PUBLIC_BASE_URL}/twiml/{audio_filename}"

    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=twiml_url,  # Twilio fetches this to know what to say
    )
    return call.sid
