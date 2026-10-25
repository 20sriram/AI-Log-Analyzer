from pathlib import Path
import sys

import pandas as pd
import requests


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "hdfs"
    / "preprocessed"
    / "Event_occurrence_matrix.csv"
)
ENDPOINT_URL = "http://127.0.0.1:8000/hdfs/predict"
EXPECTED_FEATURE_COUNT = 28

# Allow this script to be launched from a working directory other than the repo.
sys.path.insert(0, str(PROJECT_DIR))
from ai_engine.hdfs_detector import FEATURE_NAMES  # noqa: E402


def main() -> int:
    if len(FEATURE_NAMES) != EXPECTED_FEATURE_COUNT:
        print(
            "Error: the loaded HDFS model expects "
            f"{len(FEATURE_NAMES)} features, not {EXPECTED_FEATURE_COUNT}."
        )
        return 1
    if not DATA_PATH.is_file():
        print(f"Error: HDFS event-occurrence matrix not found: {DATA_PATH}")
        return 1

    try:
        sample = pd.read_csv(DATA_PATH, nrows=1)
    except (OSError, pd.errors.ParserError, UnicodeError) as error:
        print(f"Error: could not read HDFS event-occurrence matrix: {error}")
        return 1
    if sample.empty:
        print(f"Error: HDFS event-occurrence matrix has no data rows: {DATA_PATH}")
        return 1

    missing_features = [name for name in FEATURE_NAMES if name not in sample.columns]
    if missing_features:
        print(f"Error: source CSV is missing model features: {missing_features}")
        return 1

    feature_row = sample.loc[0, list(FEATURE_NAMES)]
    try:
        numeric_row = pd.to_numeric(feature_row, errors="raise")
    except (TypeError, ValueError) as error:
        print(f"Error: source row contains a non-numeric feature value: {error}")
        return 1

    features = {}
    for name in FEATURE_NAMES:
        value = numeric_row[name]
        if pd.isna(value) or value < 0 or not float(value).is_integer():
            print(
                f"Error: source feature {name!r} must be a non-negative "
                f"integer; found {value!r}."
            )
            return 1
        features[name] = int(value)

    missing_feature = dict(features)
    missing_feature.pop(FEATURE_NAMES[0])

    unexpected_feature = dict(features)
    unexpected_feature["unexpected_event"] = features[FEATURE_NAMES[0]]

    negative_feature = dict(features)
    negative_feature[FEATURE_NAMES[0]] = -1

    tests = [
        ("Valid HDFS row", {"features": dict(features)}, 200),
        ("Missing required feature", {"features": missing_feature}, 422),
        ("Unexpected feature", {"features": unexpected_feature}, 422),
        ("Negative event count", {"features": negative_feature}, 422),
    ]

    failures = 0
    for test_name, payload, expected_status in tests:
        try:
            response = requests.post(ENDPOINT_URL, json=payload, timeout=10)
        except requests.exceptions.ConnectionError:
            print(
                f"FAIL: {test_name} | Could not connect to the backend. "
                "Start it in another terminal with:\n"
                "  .\\venv\\Scripts\\python.exe -m uvicorn "
                "backend.app.main:app --reload"
            )
            return 1
        except requests.exceptions.Timeout:
            print(f"FAIL: {test_name} | Request timed out: {ENDPOINT_URL}")
            return 1
        except requests.exceptions.RequestException as error:
            print(f"FAIL: {test_name} | Request failed: {error}")
            return 1

        passed = response.status_code == expected_status
        result = None
        if test_name == "Valid HDFS row" and passed:
            try:
                result = response.json()
            except requests.exceptions.JSONDecodeError:
                passed = False
                print(f"FAIL: {test_name} | Response was not valid JSON.")
            else:
                required_fields = {"prediction", "model", "features_used"}
                if not isinstance(result, dict):
                    passed = False
                    print(
                        f"FAIL: {test_name} | Invalid response structure: {result}"
                    )
                else:
                    missing_fields = required_fields.difference(result)
                    if (
                        missing_fields
                        or result["features_used"] != EXPECTED_FEATURE_COUNT
                    ):
                        passed = False
                        print(
                            f"FAIL: {test_name} | Invalid response structure: "
                            f"{result}"
                        )

        if passed:
            print(
                f"PASS: {test_name} | HTTP {response.status_code} "
                f"(expected {expected_status})"
            )
            if result is not None:
                print(f"      JSON response: {result}")
        else:
            failures += 1
            if response.status_code != expected_status:
                print(
                    f"FAIL: {test_name} | HTTP {response.status_code} "
                    f"(expected {expected_status})"
                )

    print(f"\nValidation tests: {len(tests) - failures} passed, {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
