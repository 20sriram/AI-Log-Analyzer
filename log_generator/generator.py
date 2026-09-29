import time
import requests
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("data/logs/application.log")
REQUEST_TIMEOUT_SECONDS = 5

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def send_log(service, level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "timestamp": timestamp,
        "service": service,
        "level": level,
        "message": message
    }

    log_line = f"{timestamp} | {service} | {level} | {message}\n"

    with open(LOG_FILE, "a") as file:
        file.write(log_line)

    print(log_line.strip())

    try:
        response = requests.post(
            "http://127.0.0.1:8000/logs",
            json=data,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        print(f"Backend: log sent successfully (HTTP {response.status_code})")
    except requests.RequestException as error:
        print(f"Backend: failed to send log ({error})")


# Normal activity
send_log("user", "INFO", "User logged in")
time.sleep(1)

send_log("order", "INFO", "Order created")
time.sleep(1)

send_log("database", "INFO", "Database query executed")
time.sleep(1)

send_log("payment", "INFO", "Payment successful")
time.sleep(1)


# Failure chain
send_log("database", "ERROR", "Database connection failed")
time.sleep(1)

send_log("payment", "ERROR", "Payment service timeout")
time.sleep(1)

send_log("order", "ERROR", "Order creation failed")
time.sleep(1)

send_log("api", "ERROR", "HTTP 500 - Request failed")
time.sleep(1)


# Back to normal
send_log("user", "INFO", "User logged in")
send_log("order", "INFO", "Order created")