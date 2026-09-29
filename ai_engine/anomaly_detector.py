from sklearn.ensemble import IsolationForest


def detect_anomalies(logs):
    if len(logs) < 5:
        for log in logs:
            log["anomaly"] = False
        return logs

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

    # Detect cascading errors
    for i, log in enumerate(logs):
        if log["level"] == "ERROR":
            previous_errors = logs[max(0, i - 3):i]

            if any(
                previous["level"] == "ERROR"
                for previous in previous_errors
            ):
                log["anomaly"] = True

    return logs