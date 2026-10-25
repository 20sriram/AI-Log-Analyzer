import requests


BASE_URL = "http://127.0.0.1:8000"
EXPECTED_ANALYSIS_FIELDS = {
    "analyzed_logs",
    "related_events",
    "probable_root_cause",
    "severity",
    "confidence",
    "explanation",
}


def get_json(path: str):
    """GET an API endpoint and return its status and decoded JSON."""
    url = f"{BASE_URL}{path}"
    try:
        response = requests.get(url, timeout=10)
    except requests.exceptions.ConnectionError:
        print(
            "FAIL: Could not connect to the backend. Start it in another "
            "terminal with:\n"
            "  .\\venv\\Scripts\\python.exe -m uvicorn "
            "backend.app.main:app --reload"
        )
        return None, None
    except requests.exceptions.Timeout:
        print(f"FAIL: Request timed out: {url}")
        return None, None
    except requests.exceptions.RequestException as error:
        print(f"FAIL: Request failed for {url}: {error}")
        return None, None

    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        print(
            f"FAIL: {path} returned HTTP {response.status_code}, "
            "but its response was not valid JSON."
        )
        return response.status_code, None

    return response.status_code, payload


def main() -> int:
    failures = 0

    logs_status, logs = get_json("/logs")
    if logs_status is None:
        return 1
    if logs_status != 200:
        print(f"FAIL: GET /logs returned HTTP {logs_status} (expected 200).")
        failures += 1
    elif not isinstance(logs, list):
        print("FAIL: GET /logs returned JSON, but the response is not a list.")
        failures += 1
    else:
        print(f"PASS: GET /logs returned HTTP 200 with a list of {len(logs)} log(s).")
        if not logs:
            print("INFO: No saved application logs are currently available.")

    analysis_status, analysis = get_json("/logs/analyze")
    if analysis_status is None:
        return 1
    if analysis_status != 200:
        print(
            f"FAIL: GET /logs/analyze returned HTTP {analysis_status} "
            "(expected 200)."
        )
        failures += 1
    elif not isinstance(analysis, dict):
        print("FAIL: GET /logs/analyze returned JSON, but it is not an object.")
        failures += 1
    else:
        missing_fields = EXPECTED_ANALYSIS_FIELDS.difference(analysis)
        if missing_fields:
            print(
                "FAIL: GET /logs/analyze is missing original response field(s): "
                f"{sorted(missing_fields)}."
            )
            failures += 1
        else:
            expected_list_fields = ("analyzed_logs", "related_events")
            wrong_list_fields = [
                field for field in expected_list_fields
                if not isinstance(analysis[field], list)
            ]
            expected_scalar_types = {
                "severity": str,
                "confidence": (int, float),
                "explanation": str,
            }
            wrong_scalar_fields = [
                field
                for field, expected_type in expected_scalar_types.items()
                if not isinstance(analysis[field], expected_type)
            ]
            if wrong_list_fields or wrong_scalar_fields:
                print(
                    "FAIL: GET /logs/analyze returned the required fields, "
                    "but some values have unexpected types. "
                    f"List fields: {wrong_list_fields}; "
                    f"scalar fields: {wrong_scalar_fields}."
                )
                failures += 1
            elif analysis["probable_root_cause"] is not None and not isinstance(
                analysis["probable_root_cause"], dict
            ):
                print(
                    "FAIL: probable_root_cause must be an object or null; "
                    f"received {type(analysis['probable_root_cause']).__name__}."
                )
                failures += 1
            else:
                print(
                    "PASS: GET /logs/analyze returned HTTP 200 with all six "
                    "original response fields and expected value types."
                )

    openapi_status, openapi = get_json("/openapi.json")
    if openapi_status is None:
        return 1
    if openapi_status != 200 or not isinstance(openapi, dict):
        print(f"FAIL: Could not inspect API routes via OpenAPI (HTTP {openapi_status}).")
        failures += 1
    else:
        paths = openapi.get("paths", {})
        required_paths = {"/logs", "/logs/analyze", "/hdfs/predict"}
        absent_paths = required_paths.difference(paths)
        if absent_paths:
            print(
                "FAIL: Expected live-log and separate HDFS routes were not all "
                f"registered; missing path(s): {sorted(absent_paths)}."
            )
            failures += 1
        else:
            print(
                "PASS: OpenAPI lists /logs and /logs/analyze separately from "
                "/hdfs/predict."
            )

    print(f"\nLive API regression checks: {3 - failures} passed, {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
