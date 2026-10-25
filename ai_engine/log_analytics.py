from datetime import datetime, timedelta
from math import ceil

from ai_engine.event_correlator import parse_timestamp


def _format_interval(seconds):
    if seconds % 86400 == 0:
        days = seconds // 86400
        unit = "day" if days == 1 else "days"
        return f"{days} {unit}"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit}"
    minutes = seconds // 60
    unit = "minute" if minutes == 1 else "minutes"
    return f"{minutes} {unit}"


def build_log_analytics(logs):
    severity_counts = {
        "INFO": 0,
        "WARNING": 0,
        "ERROR": 0,
        "UNKNOWN": 0,
    }
    timestamped_logs = []

    for log in logs:
        severity = str(log.get("level") or "").strip().upper()
        if severity in severity_counts:
            severity_counts[severity] += 1
        else:
            severity_counts["UNKNOWN"] += 1

        timestamp = parse_timestamp(log.get("timestamp"))
        if timestamp is not None:
            timestamped_logs.append((timestamp, log.get("id")))

    buckets = []
    interval_seconds = None
    if timestamped_logs:
        first_time = min(timestamp for timestamp, _ in timestamped_logs)
        last_time = max(timestamp for timestamp, _ in timestamped_logs)
        span_seconds = (last_time - first_time).total_seconds()
        interval_seconds = max(300, ceil(span_seconds / 48 / 300) * 300)
        epoch = datetime(1970, 1, 1)

        counts_by_start = {}
        for timestamp, _ in timestamped_logs:
            offset = int((timestamp - epoch).total_seconds() // interval_seconds)
            bucket_start = epoch + timedelta(seconds=offset * interval_seconds)
            counts_by_start[bucket_start] = counts_by_start.get(bucket_start, 0) + 1

        first_bucket = min(counts_by_start)
        last_bucket = max(counts_by_start)
        bucket_count = int((last_bucket - first_bucket).total_seconds() // interval_seconds) + 1
        for index in range(bucket_count):
            bucket_start = first_bucket + timedelta(seconds=index * interval_seconds)
            buckets.append({
                "start": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                "count": counts_by_start.get(bucket_start, 0),
            })

    valid_timestamp_count = len(timestamped_logs)
    return {
        "total_logs": len(logs),
        "severity_counts": severity_counts,
        "invalid_timestamp_count": len(logs) - valid_timestamp_count,
        "bucket_interval_seconds": interval_seconds,
        "bucket_interval_label": (
            _format_interval(interval_seconds)
            if interval_seconds is not None
            else None
        ),
        "time_buckets": buckets,
        "log_ids": [log.get("id") for log in logs],
    }