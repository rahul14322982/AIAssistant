"""
AI Assistant — backend pipeline (Step 1 of the MVP build)

Two endpoints for now, no phone integration yet:
  POST /process-call-audio   -> Feature 1 (spam screening) core loop
  POST /generate-outbound-message -> Feature 3 (say-this-for-me) core loop

Run locally with:
  uvicorn main:app --reload
"""
import os
import shutil
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()  # must run BEFORE importing services.* — they read env vars at import time

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response

from services.telephony import place_outbound_call, PUBLIC_BASE_URL
from services.stt import transcribe_audio
from services.llm import classify_call, generate_outbound_message
from services.tts import synthesize_speech

from services.scheduler_service import (
    schedule_call,
    cancel_call,
    get_due_calls,
    mark_call_status,
)

app = FastAPI(title="AI Assistant - Call Pipeline")

TMP_DIR = "tmp_audio"
os.makedirs(TMP_DIR, exist_ok=True)

# India timezone — scheduled times from the user are assumed to be in IST
IST = ZoneInfo("Asia/Kolkata")



def generate_and_place_call(instruction: str, phone_number: str) -> dict:
    """
    Shared logic: generate the spoken message, synthesize audio, and
    place the Twilio call. Used by both the immediate and scheduled
    call endpoints.
    """
    request_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{request_id}_message.mp3")
    audio_filename = os.path.basename(output_path)

    message_text = generate_outbound_message(instruction)
    synthesize_speech(message_text, output_path)
    call_sid = place_outbound_call(phone_number, audio_filename)

    print(f"[Scheduled call fired] to={phone_number} call_sid={call_sid}")

    return {
        "instruction": instruction,
        "phone_number": phone_number,
        "message_text": message_text,
        "message_audio_url": f"/audio/{audio_filename}",
        "call_sid": call_sid,
    }



@app.get("/")
def health_check():
    return {"status": "ok", "message": "AI Assistant backend is running"}


@app.post("/process-call-audio")
async def process_call_audio(audio: UploadFile = File(...)):

    try:
        print("\n========== NEW REQUEST ==========")

        request_id = str(uuid.uuid4())

        # Preserve original audio extension
        extension = os.path.splitext(audio.filename)[1] or ".wav"

        input_path = os.path.join(
            TMP_DIR,
            f"{request_id}_input{extension}"
        )

        output_path = os.path.join(
            TMP_DIR,
            f"{request_id}_reply.mp3"
        )

        # Step 0
        print("STEP 0: Saving audio")

        with open(input_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        print("SUCCESS: Audio saved")

        # Step 1
        print("STEP 1: Deepgram transcription")

        transcript = transcribe_audio(input_path)

        print("SUCCESS: Transcript =", transcript)

        # Step 2
        print("STEP 2: LLM classification")

        result = classify_call(transcript)

        print("SUCCESS: Classification =", result)

        # Step 3
        print("STEP 3: Text to speech")

        synthesize_speech(result["reply"], output_path)

        print("SUCCESS: Speech generated")
        print("========== COMPLETE ==========\n")

        return {
            "transcript": transcript,
            "classification": result["classification"],
            "reason": result["reason"],
            "reply_text": result["reply"],
            "reply_audio_url": f"/audio/{os.path.basename(output_path)}",
        }

    except Exception as e:

        print("\n========== ERROR ==========")
        print("ERROR TYPE:", type(e).__name__)
        print("ERROR MESSAGE:", str(e))
        print("===========================\n")

        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(e).__name__,
                "message": str(e)
            }
        )

@app.post("/generate-outbound-message")
async def generate_outbound_message_endpoint(
    instruction: str = Form(...),
    phone_number: str = Form(...),
):
    """
    Feature 3 core loop: takes the user's message instruction plus the
    recipient's phone number (provided directly by the user — no contact
    lookup needed for MVP), and generates the spoken message text + audio
    that would be played on the outbound call.

    This does NOT place the call yet — that's added next with Twilio,
    using the phone_number captured here as the call target.
    """
    request_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{request_id}_message.mp3")

    # 1. Turn instruction into a natural spoken message
    message_text = generate_outbound_message(instruction)

    # 2. Text to speech
    synthesize_speech(message_text, output_path)

    return {
        "instruction": instruction,
        "phone_number": phone_number,
        "message_text": message_text,
        "message_audio_url": f"/audio/{os.path.basename(output_path)}",
    }

@app.post("/make-outbound-call")
async def make_outbound_call_endpoint(
    instruction: str = Form(...),
    phone_number: str = Form(...),
):
    """
    Feature 3, full version: generates the spoken message AND actually
    places the call via Twilio, playing that message when it connects.
    """
    request_id = str(uuid.uuid4())
    output_path = os.path.join(TMP_DIR, f"{request_id}_message.mp3")
    audio_filename = os.path.basename(output_path)

    message_text = generate_outbound_message(instruction)
    synthesize_speech(message_text, output_path)
    call_sid = place_outbound_call(phone_number, audio_filename)

    return {
        "instruction": instruction,
        "phone_number": phone_number,
        "message_text": message_text,
        "message_audio_url": f"/audio/{audio_filename}",
        "call_sid": call_sid,
        "status": "Call placed — check your phone",
    }

@app.post("/schedule-outbound-call")
async def schedule_outbound_call_endpoint(
    instruction: str = Form(...),
    phone_number: str = Form(...),
    scheduled_time: str = Form(...),
):
    """
    Feature 3, scheduled version: saves the call to Firestore instead of
    firing immediately. An external cron ping to /run-due-calls actually
    triggers it once the scheduled time arrives.

    scheduled_time format: "YYYY-MM-DD HH:MM" in 24-hour IST,
    e.g. "2026-09-05 18:30" for 6:30 PM on 5th September.
    """
    try:
        job_id = schedule_call(instruction, phone_number, scheduled_time)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "job_id": job_id,
        "instruction": instruction,
        "phone_number": phone_number,
        "scheduled_time": scheduled_time,
        "status": f"Call scheduled for {scheduled_time} IST",
    }
  
@app.delete("/schedule-outbound-call/{job_id}")
async def cancel_scheduled_call(job_id: str):
    """Cancel a previously scheduled call before it fires."""
    cancelled = cancel_call(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="No pending scheduled call found with that job_id",
        )
    return {"status": "cancelled", "job_id": job_id}

@app.post("/run-due-calls")
async def run_due_calls():
    """
    Checks Firestore for any scheduled calls whose time has arrived and
    fires them. This endpoint is meant to be pinged periodically by an
    external free cron service (e.g. cron-job.org) every 1-5 minutes —
    NOT called manually in normal use.
    """
    due = get_due_calls()
    fired = []

    for call in due:
        job_id = call["job_id"]
        try:
            result = generate_and_place_call(call["instruction"], call["phone_number"])
            mark_call_status(job_id, "completed", {"call_sid": result["call_sid"]})
            fired.append({"job_id": job_id, "status": "completed", **result})
        except Exception as e:
            mark_call_status(job_id, "failed", {"error": str(e)})
            fired.append({"job_id": job_id, "status": "failed", "error": str(e)})

    return {"checked_at": "now", "calls_fired": len(fired), "details": fired}


@app.api_route("/twiml/{filename}", methods=["GET", "POST"])
def twiml_for_audio(filename: str):
    """Twilio fetches this to find out what to say on the call."""
    audio_url = f"{PUBLIC_BASE_URL}/audio/{filename}"
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>{audio_url}</Play>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.get("/audio/{filename}")
def get_audio(filename: str):
    """Serve generated audio files so you can listen to/download results."""
    path = os.path.join(TMP_DIR, filename)
    return FileResponse(path, media_type="audio/mpeg")

@app.get("/test-error")
def test_error():
    try:
        1 / 0
    except Exception as e:
        print("TEST ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
