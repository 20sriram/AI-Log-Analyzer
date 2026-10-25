from datetime import datetime

INCIDENT_WINDOW_SECONDS = 10

RECOVERY_TERMS = (
    "recovery",
    "recovered",
    "restored",
    "resolved",
    "back to normal",
    "healthy",
    "operational",
    "resumed",
    "resuming",
    "available again",
)


def parse_timestamp(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def is_recovery_event(log):
    if log.get("level") != "INFO":
        return False

    message = str(log.get("message", "")).casefold()
    return any(term in message for term in RECOVERY_TERMS)


def correlate_events(
    logs,
    window_seconds=INCIDENT_WINDOW_SECONDS,
    include_recovery=False,
):
    problem_logs = [
        log for log in logs
        if log.get("level") in ("ERROR", "WARNING")
    ]
    problem_logs.sort(
        key=lambda log: parse_timestamp(log.get("timestamp")) or datetime.max
    )

    if not problem_logs:
        return []

    first_time = parse_timestamp(problem_logs[0].get("timestamp"))
    if first_time is None:
        return []

    related_events = []
    for log in problem_logs:
        log_time = parse_timestamp(log.get("timestamp"))
        if log_time is None:
            continue

        difference = (log_time - first_time).total_seconds()
        if 0 <= difference <= window_seconds:
            related_events.append(log)

    if not related_events:
        return []

    if not include_recovery:
        return related_events

    involved_services = {
        str(log.get("service", "")).casefold()
        for log in related_events
    }
    last_issue_time = max(
        parse_timestamp(log.get("timestamp")) for log in related_events
    )

    for log in logs:
        if not is_recovery_event(log):
            continue
        if str(log.get("service", "")).casefold() not in involved_services:
            continue

        recovery_time = parse_timestamp(log.get("timestamp"))
        if recovery_time is None:
            continue

        difference = (recovery_time - last_issue_time).total_seconds()
        if 0 < difference <= window_seconds:
            related_events.append(log)

    related_events.sort(
        key=lambda log: parse_timestamp(log.get("timestamp")) or datetime.max
    )
    return related_events


def find_root_cause(logs):
    if not logs:
        return None

    logs = sorted(
        logs,
        key=lambda log: parse_timestamp(log.get("timestamp")) or datetime.max
    )

    # Root-cause priority remains a heuristic, not evidence of causation.
    root_cause_services = [
        "database",
        "auth",
        "payment",
        "order",
        "api",
    ]

    # Check services in priority order.
    for service in root_cause_services:
        for log in logs:
            if log["service"].lower() == service:
                if log["level"] in ("ERROR", "WARNING"):
                    return log

    # If no priority service is found, return the earliest error.
    for log in logs:
        if log["level"] == "ERROR":
            return log

    return logs[0]