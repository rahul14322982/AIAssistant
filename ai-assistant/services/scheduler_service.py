"""
Scheduling service backed by Firebase Firestore.

Instead of relying on an in-process scheduler (which forgets everything
on restart), scheduled calls are stored as documents in Firestore.
A separate endpoint (/run-due-calls) is pinged periodically by an
external free cron service, checks for any calls whose time has come,
and fires them. This means scheduling survives ANY server restart,
redeploy, or crash — the source of truth lives in Firestore, not memory.
"""
import os
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

IST = ZoneInfo("Asia/Kolkata")

COLLECTION = "scheduled_calls"

# The service account key is stored as a full JSON string in one
# environment variable (FIREBASE_SERVICE_ACCOUNT_JSON) — this works
# cleanly on Railway/Render where you can't easily upload a file,
# you just paste the JSON content as a variable value.
_firebase_creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
if not _firebase_creds_json:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT_JSON is not set — paste your Firebase "
        "service account key JSON (as a single-line string) into this "
        "env var. See README for how to generate it."
    )

_cred_dict = json.loads(_firebase_creds_json)
_cred = credentials.Certificate(_cred_dict)
firebase_admin.initialize_app(_cred)

db = firestore.client()


def schedule_call(instruction: str, phone_number: str, scheduled_time_str: str) -> str:
    """
    Save a scheduled call to Firestore.

    scheduled_time_str format: "YYYY-MM-DD HH:MM" in IST.
    Returns the job_id (Firestore document ID).
    """
    run_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=IST)

    if run_time <= datetime.now(IST):
        raise ValueError("scheduled_time must be in the future")

    job_id = str(uuid.uuid4())
    doc = {
        "instruction": instruction,
        "phone_number": phone_number,
        "scheduled_time": run_time,  # Firestore stores this natively as a Timestamp
        "scheduled_time_display": scheduled_time_str,
        "status": "pending",  # pending -> completed | cancelled | failed
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(COLLECTION).document(job_id).set(doc)
    return job_id


def cancel_call(job_id: str) -> bool:
    """Cancel a pending scheduled call. Returns False if not found or not cancellable."""
    ref = db.collection(COLLECTION).document(job_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return False
    if snapshot.to_dict().get("status") != "pending":
        return False
    ref.update({"status": "cancelled"})
    return True


def get_due_calls() -> list[dict]:
    """
    Fetch all pending calls whose scheduled_time has arrived.
    Returns a list of dicts including the Firestore document id as 'job_id'.
    """
    now = datetime.now(IST)
    query = (
        db.collection(COLLECTION)
        .where("status", "==", "pending")
        .where("scheduled_time", "<=", now)
    )
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data["job_id"] = doc.id
        results.append(data)
    return results


def mark_call_status(job_id: str, status: str, extra: dict | None = None):
    """Update a call's status after attempting to fire it (completed/failed)."""
    update = {"status": status}
    if extra:
        update.update(extra)
    db.collection(COLLECTION).document(job_id).update(update)
