from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, StrictStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Log
from ai_engine.anomaly_detector import detect_anomalies
from ai_engine.event_correlator import (
    correlate_events,
    find_root_cause,
    is_recovery_event,
    parse_timestamp,
)
from ai_engine.log_analytics import build_log_analytics

router = APIRouter()
MAX_UPLOAD_SIZE_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_LINES = 20_000
MAX_REJECTED_LINE_LENGTH = 240
SUPPORTED_LOG_LEVELS = {"INFO", "WARNING", "ERROR"}
LINE_SEPARATORS = ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


class LogCreate(BaseModel):
    timestamp: StrictStr
    service: StrictStr
    level: StrictStr
    message: StrictStr


def _analyze_log_data(log_data, include_recovery=False):
    results = detect_anomalies(log_data)

    for log in results:
        log["anomaly"] = bool(log["anomaly"])

    correlated_events = correlate_events(
        results,
        include_recovery=include_recovery,
    )
    recovery_events = [
        log for log in correlated_events if is_recovery_event(log)
    ]
    related_events = [
        log for log in correlated_events if not is_recovery_event(log)
    ]
    root_cause = find_root_cause(related_events)

    severity = "LOW"
    if root_cause:
        if root_cause["level"] == "ERROR":
            severity = "HIGH"
        elif root_cause["level"] == "WARNING":
            severity = "MEDIUM"

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

    explanation = (
        "No probable root cause was selected by the existing heuristics. "
        "Confidence is a heuristic score, not a calibrated probability."
    )
    if root_cause:
        explanation = (
            f"The {root_cause['service']} service reported "
            f"'{root_cause['message']}' and was selected as the probable "
            "root-cause candidate by the existing service-priority and "
            "timestamp heuristics. Related events provide temporal context, "
            "not proof of causation. Confidence is a heuristic score, not a "
            "calibrated probability."
        )

    analysis = {
        "analyzed_logs": results,
        "related_events": related_events,
        "probable_root_cause": root_cause,
        "severity": severity,
        "confidence": confidence,
        "explanation": explanation,
    }
    if include_recovery:
        analysis["recovery_events"] = recovery_events
    return analysis


def _parse_uploaded_line(line, line_number):
    if not line.strip():
        return None, "Blank line"

    parts = [part.strip() for part in line.split("|", 3)]
    if len(parts) != 4:
        return None, "Expected timestamp | service | level | message"

    timestamp, service, level, message = parts
    if not all((timestamp, service, level, message)):
        return None, "Timestamp, service, level, and message must be non-empty"
    if parse_timestamp(timestamp) is None:
        return None, "Timestamp must use YYYY-MM-DD HH:MM:SS format"

    normalized_level = level.upper()
    if normalized_level not in SUPPORTED_LOG_LEVELS:
        return None, "Level must be INFO, WARNING, or ERROR"

    return {
        "id": line_number,
        "timestamp": timestamp,
        "service": service,
        "level": normalized_level,
        "message": message,
    }, None


def _rejected_line(line_number, line, reason):
    return {
        "line_number": line_number,
        "line": line[:MAX_REJECTED_LINE_LENGTH],
        "truncated": len(line) > MAX_REJECTED_LINE_LENGTH,
        "reason": reason,
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/logs")
def create_log(log: LogCreate, db: Session = Depends(get_db)):

    new_log = Log(
        timestamp=log.timestamp,
        service=log.service,
        level=log.level,
        message=log.message
    )

    try:
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
    except SQLAlchemyError as error:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=500,
            detail="Failed to save log",
        ) from error

    return {
        "message": "Log saved successfully",
        "id": new_log.id
    }


@router.get("/logs")
def get_logs(db: Session = Depends(get_db)):

    return db.query(Log).order_by(Log.id.desc()).all()


@router.get("/logs/analytics")
def get_log_analytics(db: Session = Depends(get_db)):
    try:
        logs = db.query(Log).order_by(Log.id.asc()).all()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve log analytics",
        ) from error

    log_data = [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "level": log.level,
        }
        for log in logs
    ]
    return build_log_analytics(log_data)


@router.get("/services/health")
def get_service_health(db: Session = Depends(get_db)):
    try:
        logs = db.query(Log).order_by(Log.id.asc()).all()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve service health",
        ) from error

    services = {}
    for log in logs:
        service_name = (
            log.service.strip()
            if isinstance(log.service, str) and log.service.strip()
            else None
        )
        service_key = service_name.casefold() if service_name else None
        service = services.setdefault(
            service_key,
            {
                "service": service_name,
                "total_logs": 0,
                "error_count": 0,
                "warning_count": 0,
                "most_recent_timestamp": None,
                "_most_recent_time": None,
            },
        )
        service["total_logs"] += 1

        level = (log.level or "").strip().upper()
        if level == "ERROR":
            service["error_count"] += 1
        elif level == "WARNING":
            service["warning_count"] += 1

        event_time = parse_timestamp(log.timestamp)
        if event_time is not None and (
            service["_most_recent_time"] is None
            or event_time > service["_most_recent_time"]
        ):
            service["_most_recent_time"] = event_time
            service["most_recent_timestamp"] = log.timestamp

    health_records = []
    for service in services.values():
        if service["error_count"] > 0:
            health_status = "Critical"
        elif service["warning_count"] > 0:
            health_status = "Warning"
        else:
            health_status = "Healthy"

        service["health_status"] = health_status
        del service["_most_recent_time"]
        health_records.append(service)

    return sorted(
        health_records,
        key=lambda service: (
            service["service"] is None,
            (service["service"] or "").casefold(),
        ),
    )


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

    return _analyze_log_data(log_data)


@router.post("/logs/analyze-file")
async def analyze_log_file(file: UploadFile = File(...)):
    filename = file.filename or ""
    extension = Path(filename.replace("\\", "/")).suffix.lower()
    if extension not in {".log", ".txt"}:
        await file.close()
        raise HTTPException(
            status_code=415,
            detail="Only .log and .txt files are supported",
        )

    try:
        if file.size is not None and file.size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds 2 MiB limit")
        contents = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    finally:
        await file.close()

    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 2 MiB limit")
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="File must contain UTF-8 text",
        ) from error

    if not text:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    line_break_count = sum(text.count(separator) for separator in LINE_SEPARATORS)
    line_count = (
        line_break_count
        - text.count("\r\n")
        + int(not text.endswith(LINE_SEPARATORS))
    )
    if line_count > MAX_UPLOAD_LINES:
        raise HTTPException(
            status_code=413,
            detail="File exceeds 20,000 line limit",
        )

    parsed_logs = []
    rejected_lines = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        log, reason = _parse_uploaded_line(line, line_number)
        if reason:
            rejected_lines.append(_rejected_line(line_number, line, reason))
        else:
            parsed_logs.append(log)

    try:
        analysis = _analyze_log_data(parsed_logs, include_recovery=True)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze uploaded log file",
        ) from error

    detected_anomalies = [
        log for log in analysis["analyzed_logs"] if log["anomaly"]
    ]
    return {
        "filename": Path(filename.replace("\\", "/")).name,
        "total_lines": len(lines),
        "parsed_logs": len(parsed_logs),
        "rejected_count": len(rejected_lines),
        "rejected_lines": rejected_lines,
        "detected_anomalies": detected_anomalies,
        **analysis,
    }