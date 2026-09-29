from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Log
from ai_engine.anomaly_detector import detect_anomalies
from ai_engine.event_correlator import correlate_events, find_root_cause

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/logs")
def create_log(log: dict, db: Session = Depends(get_db)):

    new_log = Log(
        timestamp=log["timestamp"],
        service=log["service"],
        level=log["level"],
        message=log["message"]
    )

    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return {
        "message": "Log saved successfully",
        "id": new_log.id
    }


@router.get("/logs")
def get_logs(db: Session = Depends(get_db)):

    return db.query(Log).order_by(Log.id.desc()).all()


@router.get("/logs/analyze")
def analyze_logs(db: Session = Depends(get_db)):

    # Get all logs from database
    logs = db.query(Log).all()

    # Convert database logs into dictionaries
    log_data = [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "service": log.service,
            "level": log.level,
            "message": log.message
        }
        for log in logs
    ]

    # Detect anomalies using AI
    results = detect_anomalies(log_data)

    # Convert NumPy boolean to normal Python boolean
    for log in results:
        log["anomaly"] = bool(log["anomaly"])

    # Find related events
    related_events = correlate_events(results)

    # Find probable root cause
    root_cause = find_root_cause(related_events)

    # Calculate severity
    severity = "LOW"

    if root_cause:

        if root_cause["level"] == "ERROR":
            severity = "HIGH"

        elif root_cause["level"] == "WARNING":
            severity = "MEDIUM"

    # Calculate confidence
    confidence = 0.50

    if root_cause and related_events:

        if root_cause["level"] == "ERROR":
            confidence += 0.10

        if len(related_events) >= 2:
            confidence += 0.10

        if len(related_events) >= 4:
            confidence += 0.10

        first_event = related_events[0]

        if root_cause["id"] == first_event["id"]:
            confidence += 0.10

        if root_cause["service"] == "database":
            confidence += 0.05

        confidence = min(confidence, 0.95)

    # Generate explanation
    explanation = "No root cause detected."

    if root_cause:
        explanation = (
            f"The {root_cause['service']} service reported "
            f"'{root_cause['message']}' first. "
            "The following errors occurred shortly after it, "
            "indicating that this failure is the probable root cause "
            "of the incident."
        )

    # Final response
    return {
        "analyzed_logs": results,
        "related_events": related_events,
        "probable_root_cause": root_cause,
        "severity": severity,
        "confidence": confidence,
        "explanation": explanation
    }