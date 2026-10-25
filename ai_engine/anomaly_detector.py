from ai_engine.event_correlator import parse_timestamp
from sklearn.ensemble import IsolationForest

CASCADE_WINDOW_SECONDS = 10


def detect_anomalies(logs):
    if len(logs) >= 5:
        features = []

        for log in logs:
            features.append([
                1 if log["level"] == "ERROR" else 0,
                1 if log["level"] == "WARNING" else 0,
                len(log["message"]),
                len(log["service"])
            ])

        model = IsolationForest(
            contamination=0.1,
            random_state=42
        )

        predictions = model.fit_predict(features)

        for log, prediction in zip(logs, predictions):
            log["anomaly"] = prediction == -1
    else:
        for log in logs:
            log["anomaly"] = False

    error_events = [
        (parse_timestamp(log.get("timestamp")), index)
        for index, log in enumerate(logs)
        if log["level"] == "ERROR"
    ]
    error_events = [
        (timestamp, index)
        for timestamp, index in error_events
        if timestamp is not None
    ]
    error_events.sort(key=lambda event: event[0])

    for position, (event_time, log_index) in enumerate(error_events):
        has_nearby_previous = (
            position > 0
            and (event_time - error_events[position - 1][0]).total_seconds()
            <= CASCADE_WINDOW_SECONDS
        )
        has_nearby_next = (
            position + 1 < len(error_events)
            and (error_events[position + 1][0] - event_time).total_seconds()
            <= CASCADE_WINDOW_SECONDS
        )
        if has_nearby_previous or has_nearby_next:
            logs[log_index]["anomaly"] = True

    return logs