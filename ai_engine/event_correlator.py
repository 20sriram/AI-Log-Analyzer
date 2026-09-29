from datetime import datetime


def parse_timestamp(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def correlate_events(logs, window_seconds=10):

    problem_logs = [
        log for log in logs
        if log.get("level") in ("ERROR", "WARNING")
    ]

    if not problem_logs:
        return []

    problem_logs.sort(
        key=lambda x: parse_timestamp(x["timestamp"]) or datetime.max
    )

    first_time = parse_timestamp(problem_logs[0]["timestamp"])

    if first_time is None:
        return problem_logs

    related_events = []

    for log in problem_logs:

        log_time = parse_timestamp(log["timestamp"])

        if log_time is None:
            continue

        difference = (
            log_time - first_time
        ).total_seconds()

        if 0 <= difference <= window_seconds:
            related_events.append(log)

    return related_events


def find_root_cause(logs):

    if not logs:
        return None

    logs = sorted(
        logs,
        key=lambda x: parse_timestamp(x["timestamp"]) or datetime.max
    )

    # Root-cause priority
    root_cause_services = [
        "database",
        "auth",
        "payment",
        "order",
        "api"
    ]

    # Check services in priority order
    for service in root_cause_services:

        for log in logs:

            if log["service"].lower() == service:

                if log["level"] in ("ERROR", "WARNING"):

                    return log

    # If no priority service is found,
    # return the earliest error
    for log in logs:

        if log["level"] == "ERROR":
            return log

    return logs[0]