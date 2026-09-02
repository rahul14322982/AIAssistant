"""
LLM service: classifies call transcripts as SPAM or GENUINE,
and generates a short spoken reply.
"""
import os
import json
from openai import OpenAI

# OpenRouter is OpenAI-SDK compatible — just point base_url at their endpoint
# and use an OpenRouter API key. Get one at https://openrouter.ai/keys
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# Pick any model OpenRouter supports, e.g.:
#   "openai/gpt-4o-mini"
#   "anthropic/claude-3.5-haiku"
#   "meta-llama/llama-3.1-8b-instruct"
# See https://openrouter.ai/models for the full list + pricing
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

CLASSIFY_SYSTEM_PROMPT = """You are a call-screening assistant for a phone user in India.
You will be given a transcript of what a caller said after the phone was picked up
by an AI assistant on the user's behalf.

Decide if this call is:
- SPAM: telemarketing, robocalls, loan/credit card offers, scam attempts,
  "your KYC is pending" style scam calls, insurance cold-calls, survey calls
- GENUINE: a real person calling for a real reason (friend, family, colleague,
  delivery person, doctor's office, genuine business callback the user is expecting)

Respond ONLY with valid JSON in this exact shape, nothing else:
{"classification": "SPAM" or "GENUINE", "reason": "one short sentence why", "reply": "a short polite spoken reply appropriate to the classification"}

If SPAM: the reply should politely decline and end the call, e.g.
"Thank you, but we're not interested. Please remove this number from your list. Goodbye."

If GENUINE: the reply should let the caller know their call is being noted
and the person will get back to them, e.g.
"Thanks for calling, I've noted your message and the person will call you back shortly."
"""


def classify_call(transcript: str) -> dict:
    """
    Classify a call transcript as SPAM or GENUINE and generate a reply.

    Args:
        transcript: what the caller said, as text

    Returns:
        dict with keys: classification, reason, reply
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Caller said: \"{transcript}\""},
        ],
        temperature=0.3,
        max_tokens=50
    )
    content = response.choices[0].message.content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Fallback if the model returns malformed JSON
        return {
            "classification": "GENUINE",
            "reason": "Could not parse classification, defaulting to safe option",
            "reply": "Thanks for calling, I've noted your message and the person will call you back shortly.",
        }


def generate_outbound_message(user_instruction: str) -> str:
    """
    Given the phone owner's instruction (e.g. "tell Rajesh I'll be 20 min late"),
    generate the exact sentence the AI should speak on the outbound call.

    Args:
        user_instruction: what the user typed/said they want communicated

    Returns:
        A natural, spoken-style message ready for TTS.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You turn a short instruction from a phone user into a natural, "
                    "polite, spoken message that an AI assistant will read aloud on a call "
                    "on the user's behalf. Keep it brief, conversational, and first-person "
                    "as if the assistant is speaking for the user. Respond with ONLY the "
                    "message text, nothing else."
                ),
            },
            {"role": "user", "content": user_instruction},
        ],
        temperature=0.5,
        max_tokens=50
    )
    return response.choices[0].message.content.strip()
