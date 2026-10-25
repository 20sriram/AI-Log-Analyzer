from numbers import Integral
from pathlib import Path

import joblib
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_DIR / "ml" / "models" / "hdfs_random_forest_grouped.joblib"

if not MODEL_PATH.is_file():
    raise FileNotFoundError(
        "The trained HDFS Random Forest model was not found at "
        f"{MODEL_PATH}. Train and save the grouped HDFS model before using "
        "the HDFS detector."
    )

try:
    _MODEL = joblib.load(MODEL_PATH)
except Exception as error:
    raise RuntimeError(
        f"Could not load the trained HDFS model at {MODEL_PATH}: {error}"
    ) from error

if not hasattr(_MODEL, "feature_names_in_"):
    raise ValueError(
        f"The model at {MODEL_PATH} does not contain feature_names_in_; "
        "its expected input columns cannot be determined safely."
    )

# Use the saved model's own column names and order rather than duplicating them.
FEATURE_NAMES = tuple(str(name) for name in _MODEL.feature_names_in_)
if not FEATURE_NAMES or len(set(FEATURE_NAMES)) != len(FEATURE_NAMES):
    raise ValueError(
        f"The model at {MODEL_PATH} has missing or duplicate feature names."
    )


def predict_hdfs_block(features: dict) -> dict:
    """Classify one HDFS event-count pattern as Normal or Anomaly."""
    if not isinstance(features, dict):
        raise TypeError("features must be a dictionary of event-count values.")

    provided_names = set(features)
    expected_names = set(FEATURE_NAMES)
    missing_names = [name for name in FEATURE_NAMES if name not in provided_names]
    unexpected_names = sorted(
        (repr(name) for name in provided_names - expected_names)
    )
    if missing_names or unexpected_names:
        details = []
        if missing_names:
            details.append(f"missing feature(s): {missing_names}")
        if unexpected_names:
            details.append(f"unexpected feature name(s): {unexpected_names}")
        raise ValueError("Invalid HDFS features; " + "; ".join(details))

    for name in FEATURE_NAMES:
        value = features[name]
        # bool is an Integral subclass in Python, but is not an event count.
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(
                f"Feature {name!r} must be a non-negative integer; "
                f"received {value!r}."
            )
        if value < 0:
            raise ValueError(
                f"Feature {name!r} must be non-negative; received {value!r}."
            )

    # Construct columns in the exact order used when the model was trained.
    model_input = pd.DataFrame(
        [[features[name] for name in FEATURE_NAMES]],
        columns=FEATURE_NAMES,
    )
    try:
        predicted_class = _MODEL.predict(model_input)[0]
    except Exception as error:
        raise RuntimeError(
            f"HDFS model prediction failed for {len(FEATURE_NAMES)} features: "
            f"{error}"
        ) from error

    if predicted_class == 0:
        prediction = "Normal"
    elif predicted_class == 1:
        prediction = "Anomaly"
    else:
        raise ValueError(
            "The HDFS model returned an unexpected class value: "
            f"{predicted_class!r}."
        )

    return {
        "prediction": prediction,
        "model": "HDFS Random Forest",
        "features_used": len(FEATURE_NAMES),
    }
