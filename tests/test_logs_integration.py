import asyncio
import io
import os
import sqlite3
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LogPersistenceIntegrationTests(unittest.TestCase):
    def test_log_analytics_endpoint_reports_database_counts_and_ids(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                logs = [
                    ("2026-10-22 10:01:00", "INFO"),
                    ("2026-10-22 10:07:00", "ERROR"),
                    ("2026-10-22 10:08:00", "WARNING"),
                    ("bad timestamp", "DEBUG"),
                ]
                for index, (timestamp, level) in enumerate(logs):
                    response = requests.post(
                        f"{base_url}/logs",
                        json={
                            "timestamp": timestamp,
                            "service": "analytics-test",
                            "level": level,
                            "message": f"analytics event {index}",
                        },
                        timeout=5,
                    )
                    self.assertEqual(response.status_code, 200, response.text)

                analytics_response = requests.get(
                    f"{base_url}/logs/analytics",
                    timeout=5,
                )
                self.assertEqual(
                    analytics_response.status_code,
                    200,
                    analytics_response.text,
                )
                analytics = analytics_response.json()
                self.assertEqual(analytics["total_logs"], 4)
                self.assertEqual(
                    analytics["severity_counts"],
                    {"INFO": 1, "WARNING": 1, "ERROR": 1, "UNKNOWN": 1},
                )
                self.assertEqual(analytics["invalid_timestamp_count"], 1)
                self.assertEqual(
                    [bucket["count"] for bucket in analytics["time_buckets"]],
                    [1, 2],
                )

                analysis_response = requests.get(
                    f"{base_url}/logs/analyze",
                    timeout=5,
                )
                self.assertEqual(analysis_response.status_code, 200)
                self.assertEqual(
                    analytics["log_ids"],
                    [log["id"] for log in analysis_response.json()["analyzed_logs"]],
                )

    def test_log_analytics_database_failure_returns_generic_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute("DROP TABLE logs")
                    connection.commit()
                finally:
                    connection.close()

                response = requests.get(
                    f"{base_url}/logs/analytics",
                    timeout=5,
                )
                self.assertEqual(response.status_code, 500)
                self.assertEqual(
                    response.json(),
                    {"detail": "Failed to retrieve log analytics"},
                )
                self.assertNotIn("sqlite", response.text.casefold())
                self.assertNotIn(str(database_path), response.text)

    def test_log_analytics_empty_database_returns_empty_aggregates(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                response = requests.get(
                    f"{base_url}/logs/analytics",
                    timeout=5,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total_logs"], 0)
                self.assertEqual(
                    response.json()["severity_counts"],
                    {"INFO": 0, "WARNING": 0, "ERROR": 0, "UNKNOWN": 0},
                )
                self.assertEqual(response.json()["time_buckets"], [])
                self.assertEqual(response.json()["log_ids"], [])

    def test_service_health_counts_statuses_and_latest_timestamps(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                logs = [
                    ("2026-10-22 10:00:01", "Payment", "ERROR", "Charge failed"),
                    ("2026-10-22 10:00:02", "Payment", "WARNING", "Retry scheduled"),
                    ("2026-10-22 10:00:03", "payment", "INFO", "Charge recovered"),
                    ("2026-10-22 10:01:01", "Billing", "WARNING", "Queue delayed"),
                    ("2026-10-22 10:01:02", "Billing", "INFO", "Queue checked"),
                    ("2026-10-22 10:02:00", "Telemetry", "INFO", "Heartbeat"),
                    ("2026-10-22 10:03:00", "UnconfiguredWorker", "INFO", "Started"),
                    ("2026-10-22 10:04:00", "   ", "WARNING", "Service name missing"),
                ]
                for timestamp, service, level, message in logs:
                    response = requests.post(
                        f"{base_url}/logs",
                        json={
                            "timestamp": timestamp,
                            "service": service,
                            "level": level,
                            "message": message,
                        },
                        timeout=5,
                    )
                    self.assertEqual(response.status_code, 200, response.text)

                response = requests.get(f"{base_url}/services/health", timeout=5)
                self.assertEqual(response.status_code, 200, response.text)
                health_by_service = {
                    service["service"]: service for service in response.json()
                }

                payment = health_by_service["Payment"]
                self.assertEqual(payment["total_logs"], 3)
                self.assertEqual(payment["error_count"], 1)
                self.assertEqual(payment["warning_count"], 1)
                self.assertEqual(
                    payment["most_recent_timestamp"], "2026-10-22 10:00:03"
                )
                self.assertEqual(payment["health_status"], "Critical")

                billing = health_by_service["Billing"]
                self.assertEqual(billing["total_logs"], 2)
                self.assertEqual(billing["error_count"], 0)
                self.assertEqual(billing["warning_count"], 1)
                self.assertEqual(
                    billing["most_recent_timestamp"], "2026-10-22 10:01:02"
                )
                self.assertEqual(billing["health_status"], "Warning")

                telemetry = health_by_service["Telemetry"]
                self.assertEqual(telemetry["health_status"], "Healthy")
                self.assertEqual(telemetry["total_logs"], 1)

                unknown_service = health_by_service["UnconfiguredWorker"]
                self.assertEqual(unknown_service["health_status"], "Healthy")
                self.assertEqual(
                    health_by_service[None]["health_status"], "Warning"
                )
                self.assertEqual(health_by_service[None]["total_logs"], 1)

    def test_service_health_returns_empty_list_for_empty_database(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                response = requests.get(f"{base_url}/services/health", timeout=5)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])

    def test_service_health_database_failure_returns_sanitized_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute("DROP TABLE logs")
                    connection.commit()
                finally:
                    connection.close()

                response = requests.get(f"{base_url}/services/health", timeout=5)

                self.assertEqual(response.status_code, 500)
                self.assertEqual(
                    response.json(),
                    {"detail": "Failed to retrieve service health"},
                )
                self.assertNotIn("sqlite", response.text.casefold())
                self.assertNotIn(str(database_path), response.text)

    def test_incident_analysis_api_failure_returns_server_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute("DROP TABLE logs")
                    connection.commit()
                finally:
                    connection.close()

                response = requests.get(f"{base_url}/logs/analyze", timeout=5)

                self.assertEqual(response.status_code, 500)
                self.assertNotIn(str(database_path), response.text)
                self.assertNotIn("sqlite", response.text.casefold())

    def test_incident_analysis_api_failure_preserves_generic_http_response(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                connection = sqlite3.connect(database_path)
                try:
                    connection.execute("DROP TABLE logs")
                    connection.commit()
                finally:
                    connection.close()

                response = requests.get(f"{base_url}/logs/analyze", timeout=5)

                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.text, "Internal Server Error")

    def test_upload_analyzes_application_logs_without_database_inserts(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                log_text = "\n".join(
                    (
                        "2026-10-22 12:00:00 | user | INFO | User logged in",
                        "2026-10-22 12:00:01 | order | INFO | Order created",
                        "2026-10-22 12:00:02 | database | ERROR | Database unavailable",
                        "2026-10-22 12:00:04 | payment | ERROR | Payment timed out",
                        "2026-10-22 12:00:06 | order | ERROR | Order failed",
                        "2026-10-22 12:00:08 | api | ERROR | Request failed",
                    )
                )
                response = self._upload_file(
                    base_url,
                    "application.log",
                    log_text.encode("utf-8"),
                )

                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["total_lines"], 6)
                self.assertEqual(result["parsed_logs"], 6)
                self.assertEqual(result["rejected_count"], 0)
                self.assertEqual(result["rejected_lines"], [])
                self.assertEqual(result["recovery_events"], [])
                self.assertEqual(len(result["analyzed_logs"]), 6)
                self.assertTrue(
                    all(isinstance(log["anomaly"], bool) for log in result["analyzed_logs"])
                )
                self.assertEqual(
                    result["probable_root_cause"]["service"], "database"
                )
                self.assertEqual(result["severity"], "HIGH")
                self.assertIsInstance(result["confidence"], (int, float))
                self.assertTrue(result["explanation"])

                stored_logs = requests.get(f"{base_url}/logs", timeout=5)
                self.assertEqual(stored_logs.status_code, 200)
                self.assertEqual(stored_logs.json(), [])
                stored_analytics = requests.get(
                    f"{base_url}/logs/analytics",
                    timeout=5,
                )
                self.assertEqual(stored_analytics.status_code, 200)
                self.assertEqual(stored_analytics.json()["total_logs"], 0)
                self.assertEqual(stored_analytics.json()["log_ids"], [])

                stored_analysis = requests.get(
                    f"{base_url}/logs/analyze",
                    timeout=5,
                )
                self.assertEqual(stored_analysis.status_code, 200)
                self.assertEqual(
                    set(stored_analysis.json()),
                    {
                        "analyzed_logs",
                        "related_events",
                        "probable_root_cause",
                        "severity",
                        "confidence",
                        "explanation",
                    },
                )
                self.assertEqual(stored_analysis.json()["analyzed_logs"], [])

    def test_dummy_incident_flags_initial_error_and_separates_recovery(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                lines = [
                    "2026-10-22 10:00:00 | UserService | INFO | Session started",
                    "2026-10-22 10:00:02 | GatewayService | INFO | Request accepted",
                    "2026-10-22 10:00:05 | CatalogService | INFO | Catalog loaded",
                    "2026-10-22 10:00:10 | CacheService | INFO | Cache checked",
                    "2026-10-22 10:00:15 | AuthService | INFO | User authenticated",
                    "2026-10-22 10:00:22 | PaymentService | ERROR | Database connection failed during payment request",
                    "2026-10-22 10:00:24 | PaymentService | ERROR | Payment request failed",
                    "2026-10-22 10:00:27 | OrderService | ERROR | Order processing failed",
                    "2026-10-22 10:00:30 | ApiService | ERROR | Request returned HTTP 500",
                    "2026-10-22 10:00:36 | PaymentService | INFO | Payment service recovered",
                    "2026-10-22 10:00:37 | StorageService | INFO | Storage service recovered",
                    "2026-10-22 10:00:38 | OrderService | INFO | Order processing resumed",
                ]
                lines.extend(
                    f"2026-10-22 11:00:{second:02d} | AuditService | INFO | Heartbeat {second}"
                    for second in range(13)
                )
                self.assertEqual(len(lines), 25)

                response = self._upload_file(
                    base_url,
                    "dummy_application.log",
                    "\n".join(lines).encode("utf-8"),
                )

                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["total_lines"], 25)
                self.assertEqual(result["parsed_logs"], 25)
                self.assertEqual(result["rejected_count"], 0)

                root_cause = result["probable_root_cause"]
                self.assertEqual(root_cause["id"], 6)
                self.assertEqual(root_cause["service"], "PaymentService")
                self.assertEqual(
                    root_cause["message"],
                    "Database connection failed during payment request",
                )
                anomaly_ids = {
                    log["id"] for log in result["detected_anomalies"]
                }
                self.assertIn(root_cause["id"], anomaly_ids)

                related_ids = [
                    log["id"] for log in result["related_events"]
                ]
                self.assertEqual(related_ids, [6, 7, 8, 9])
                recovery_events = result["recovery_events"]
                self.assertEqual(
                    [log["timestamp"] for log in recovery_events],
                    [
                        "2026-10-22 10:00:36",
                        "2026-10-22 10:00:38",
                    ],
                )
                self.assertEqual(
                    [log["id"] for log in recovery_events], [10, 12]
                )
                self.assertTrue(anomaly_ids.isdisjoint({10, 12}))
                self.assertNotIn(10, related_ids)
                self.assertNotIn(11, related_ids)
                self.assertNotIn(11, [log["id"] for log in recovery_events])
                self.assertIn("not proof of causation", result["explanation"])
                self.assertIn(
                    "not a calibrated probability",
                    result["explanation"],
                )

                stored_logs = requests.get(f"{base_url}/logs", timeout=5)
                self.assertEqual(stored_logs.status_code, 200)
                self.assertEqual(stored_logs.json(), [])

    def test_normal_logs_and_incident_without_recovery(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                normal_lines = [
                    f"2026-10-22 09:00:{second:02d} | WebService | INFO | Request {second} completed"
                    for second in range(5)
                ]
                normal_response = self._upload_file(
                    base_url,
                    "normal.log",
                    "\n".join(normal_lines).encode("utf-8"),
                )
                self.assertEqual(normal_response.status_code, 200)
                normal_result = normal_response.json()
                self.assertIsNone(normal_result["probable_root_cause"])
                self.assertEqual(normal_result["related_events"], [])
                self.assertEqual(normal_result["recovery_events"], [])
                self.assertEqual(normal_result["detected_anomalies"], [])
                self.assertEqual(normal_result["severity"], "LOW")

                incident_lines = normal_lines + [
                    "2026-10-22 10:00:22 | PaymentService | ERROR | Database connection failed during payment request",
                    "2026-10-22 10:00:24 | PaymentService | ERROR | Payment request failed",
                    "2026-10-22 10:00:27 | OrderService | ERROR | Order processing failed",
                ]
                incident_response = self._upload_file(
                    base_url,
                    "incident-no-recovery.txt",
                    "\n".join(incident_lines).encode("utf-8"),
                )
                self.assertEqual(incident_response.status_code, 200)
                incident_result = incident_response.json()
                self.assertEqual(
                    incident_result["probable_root_cause"]["message"],
                    "Database connection failed during payment request",
                )
                self.assertEqual(incident_result["recovery_events"], [])
                self.assertEqual(
                    [log["level"] for log in incident_result["related_events"]],
                    ["ERROR", "ERROR", "ERROR"],
                )

    def test_single_root_candidate_is_not_forced_into_anomaly_list(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                lines = [
                    "2026-10-22 10:00:00 | UserService | INFO | Session started",
                    "2026-10-22 10:00:05 | CatalogService | INFO | Catalog loaded",
                    "2026-10-22 10:00:10 | PaymentService | ERROR | Database connection failed during payment request",
                    "2026-10-22 10:00:40 | AuditService | INFO | Health check completed",
                ]
                response = self._upload_file(
                    base_url,
                    "isolated-error.log",
                    "\n".join(lines).encode("utf-8"),
                )

                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(
                    result["probable_root_cause"]["id"], 3
                )
                self.assertEqual(result["related_events"][0]["id"], 3)
                self.assertEqual(result["detected_anomalies"], [])

    def test_empty_upload_returns_client_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                response = self._upload_file(base_url, "empty.log", b"")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], "Uploaded file is empty")

    def test_non_utf8_upload_returns_client_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                response = self._upload_file(
                    base_url,
                    "invalid-encoding.log",
                    b"\xff\xfe\xfa",
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["detail"],
                    "File must contain UTF-8 text",
                )

    def test_unsupported_upload_extension_returns_client_error(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                response = self._upload_file(base_url, "application.csv", b"a,b\n")

                self.assertEqual(response.status_code, 415)

    def test_oversized_upload_returns_payload_too_large(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                contents = b"x" * (2 * 1024 * 1024 + 1)
                response = self._upload_file(base_url, "oversized.log", contents)

                self.assertEqual(response.status_code, 413)

    def test_upload_exceeding_line_limit_returns_payload_too_large(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                for separator in (b"\n", b"\v"):
                    with self.subTest(separator=separator):
                        contents = separator * 20_001
                        response = self._upload_file(
                            base_url,
                            "many-lines.log",
                            contents,
                        )
                        self.assertEqual(response.status_code, 413)

    def test_malformed_lines_are_reported_without_failing_valid_lines(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                log_text = "\n".join(
                    (
                        "2026-10-22 12:00:00 | user | INFO | User logged in",
                        "not a structured log line",
                        "2026-10-22 12:00:02 | database | ERROR | Database unavailable",
                    )
                )
                response = self._upload_file(
                    base_url,
                    "mixed.txt",
                    log_text.encode("utf-8"),
                )

                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["total_lines"], 3)
                self.assertEqual(result["parsed_logs"], 2)
                self.assertEqual(result["rejected_count"], 1)
                self.assertEqual(result["rejected_lines"][0]["line_number"], 2)
                self.assertEqual(
                    result["rejected_lines"][0]["line"],
                    "not a structured log line",
                )

    def test_analysis_failure_returns_sanitized_server_error(self):
        from fastapi import HTTPException, UploadFile

        from backend.app.routes.logs import analyze_log_file

        upload = UploadFile(
            filename="failure.log",
            file=io.BytesIO(
                b"2026-10-22 12:00:00 | database | ERROR | Database unavailable"
            ),
        )
        secret_detail = "postgresql://test-user:top-secret@db.internal/log_analyzer"

        with patch(
            "backend.app.routes.logs._analyze_log_data",
            side_effect=RuntimeError(secret_detail),
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(analyze_log_file(upload))

        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(
            error.exception.detail,
            "Failed to analyze uploaded log file",
        )
        self.assertNotIn("top-secret", error.exception.detail)

    def test_cors_allows_both_local_frontend_origins(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                allowed_origins = (
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                )

                for origin in allowed_origins:
                    with self.subTest(origin=origin):
                        response = requests.get(
                            f"{base_url}/",
                            headers={"Origin": origin},
                            timeout=5,
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.headers.get("access-control-allow-origin"),
                            origin,
                        )
                        self.assertEqual(
                            response.headers.get(
                                "access-control-allow-credentials"
                            ),
                            "true",
                        )

    def test_posted_log_is_persisted_and_returned_by_get(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                unique_id = uuid.uuid4().hex
                submitted_log = {
                    "timestamp": "2026-10-22 12:34:56",
                    "service": f"integration-test-{unique_id}",
                    "level": "INFO",
                    "message": f"persistence-check-{unique_id}",
                }

                post_response = requests.post(
                    f"{base_url}/logs",
                    json=submitted_log,
                    timeout=5,
                )
                self.assertEqual(post_response.status_code, 200)
                self.assertEqual(
                    post_response.json().get("message"),
                    "Log saved successfully",
                )
                self.assertIsInstance(post_response.json().get("id"), int)

                get_response = requests.get(f"{base_url}/logs", timeout=5)
                self.assertEqual(get_response.status_code, 200)
                logs = get_response.json()
                matching_logs = [
                    log for log in logs
                    if log.get("message") == submitted_log["message"]
                ]

                self.assertEqual(len(matching_logs), 1)
                saved_log = matching_logs[0]
                for field, expected_value in submitted_log.items():
                    with self.subTest(field=field):
                        self.assertEqual(saved_log.get(field), expected_value)

    def test_invalid_post_payloads_return_422_without_saving(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            with self._test_server(database_path) as base_url:
                unique_id = uuid.uuid4().hex
                valid_payload = {
                    "timestamp": "2026-10-22 12:34:56",
                    "service": f"integration-test-{unique_id}",
                    "level": "INFO",
                    "message": f"invalid-payload-check-{unique_id}",
                }
                missing_field = dict(valid_payload)
                del missing_field["message"]
                invalid_service_type = {
                    **valid_payload,
                    "service": 123,
                }
                invalid_message_type = {
                    **valid_payload,
                    "message": None,
                }

                invalid_payloads = (
                    ("missing required field", missing_field),
                    ("numeric service", invalid_service_type),
                    ("null message", invalid_message_type),
                )
                for case_name, payload in invalid_payloads:
                    with self.subTest(case=case_name):
                        response = requests.post(
                            f"{base_url}/logs",
                            json=payload,
                            timeout=5,
                        )
                        self.assertEqual(response.status_code, 422)

                get_response = requests.get(f"{base_url}/logs", timeout=5)
                self.assertEqual(get_response.status_code, 200)
                self.assertEqual(get_response.json(), [])

    def test_database_failure_returns_sanitized_error_and_saves_nothing(self):
        with tempfile.TemporaryDirectory(prefix="ai-log-analyzer-test-") as directory:
            database_path = Path(directory) / "integration.sqlite3"
            secret_connection_string = (
                "postgresql://test-user:top-secret@db.internal/log_analyzer"
            )
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """CREATE TABLE logs (
                        id INTEGER NOT NULL PRIMARY KEY,
                        timestamp VARCHAR,
                        service VARCHAR,
                        level VARCHAR,
                        message TEXT
                    )"""
                )
                connection.execute(
                    """CREATE TRIGGER fail_log_insert
                    BEFORE INSERT ON logs
                    BEGIN
                        SELECT RAISE(ABORT, 'postgresql://test-user:top-secret@db.internal/log_analyzer');
                    END"""
                )
                connection.commit()
            finally:
                connection.close()

            with self._test_server(database_path) as base_url:
                unique_id = uuid.uuid4().hex
                submitted_log = {
                    "timestamp": "2026-10-22 12:34:56",
                    "service": f"integration-test-{unique_id}",
                    "level": "INFO",
                    "message": f"database-failure-check-{unique_id}",
                }
                response = requests.post(
                    f"{base_url}/logs",
                    json=submitted_log,
                    timeout=5,
                )

                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json(), {"detail": "Failed to save log"})
                self.assertNotIn(secret_connection_string, response.text)
                self.assertNotIn("top-secret", response.text)

                get_response = requests.get(f"{base_url}/logs", timeout=5)
                self.assertEqual(get_response.status_code, 200)
                self.assertEqual(get_response.json(), [])

    @contextmanager
    def _test_server(self, database_path):
        environment = os.environ.copy()
        environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        base_url = f"http://127.0.0.1:{port}"

        try:
            self._wait_for_server(process, base_url)
            yield base_url
        finally:
            self._stop_server(process)

    def _wait_for_server(self, process, base_url):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail(
                    f"Test API process exited during startup with code {process.returncode}"
                )
            try:
                response = requests.get(f"{base_url}/", timeout=0.5)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.1)

        self.fail("Test API did not become ready within 15 seconds")

    def _upload_file(self, base_url, filename, contents):
        return requests.post(
            f"{base_url}/logs/analyze-file",
            files={"file": (filename, contents, "text/plain")},
            timeout=15,
        )

    def _stop_server(self, process):
        if process.poll() is None:
            try:
                stop_signal = (
                    signal.CTRL_BREAK_EVENT
                    if os.name == "nt"
                    else signal.SIGINT
                )
                process.send_signal(stop_signal)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()