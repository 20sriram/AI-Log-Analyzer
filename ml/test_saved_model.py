from pathlib import Path

import joblib
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_DIR / "ml" / "models" / "hdfs_random_forest_grouped.joblib"
DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "hdfs"
    / "preprocessed"
    / "Event_occurrence_matrix.csv"
)
SAMPLE_SIZE = 10

# This is the training order used by validate_grouped.py after dropping E22.
EXPECTED_FEATURES = [
    f"E{index}"
    for index in range(1, 30)
    if index != 22
]
CLASS_NAMES = {0: "Normal", 1: "Anomaly"}
ACTUAL_LABELS = {
    "Normal": "Normal",
    "Anomaly": "Anomaly",
    "Success": "Normal",
    "Fail": "Anomaly",
}


def main() -> None:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Grouped model file not found: {MODEL_PATH}")
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Event-occurrence matrix not found: {DATA_PATH}")

    try:
        model = joblib.load(MODEL_PATH)
    except Exception as error:
        raise RuntimeError(
            f"Could not load the saved model at {MODEL_PATH}: {error}"
        ) from error

    model_feature_names = getattr(model, "feature_names_in_", None)
    if model_feature_names is None:
        raise ValueError(
            "The saved model does not expose feature_names_in_; cannot verify "
            "the expected feature names and order."
        )
    model_feature_names = list(model_feature_names)
    print("Model expected feature names:")
    print(model_feature_names)

    if model_feature_names != EXPECTED_FEATURES:
        raise ValueError(
            "The saved model feature names/order do not match the expected 28 "
            "features (E1-E29 excluding E22). The model expects "
            f"{len(model_feature_names)} feature(s): {model_feature_names}"
        )

    try:
        sample = pd.read_csv(DATA_PATH, nrows=SAMPLE_SIZE)
    except Exception as error:
        raise RuntimeError(
            f"Could not read event-occurrence matrix at {DATA_PATH}: {error}"
        ) from error

    if len(sample) < SAMPLE_SIZE:
        raise ValueError(
            f"Expected at least {SAMPLE_SIZE} data rows in {DATA_PATH}, "
            f"but found {len(sample)}."
        )

    missing_columns = [
        column for column in model_feature_names if column not in sample.columns
    ]
    if missing_columns:
        raise ValueError(
            "Event-occurrence matrix is missing model feature column(s): "
            f"{missing_columns}"
        )

    try:
        features = sample.loc[:, model_feature_names].apply(
            pd.to_numeric, errors="raise"
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "One or more model input feature values are not numeric."
        ) from error
    if features.isna().any().any():
        raise ValueError("Model input features contain missing values.")

    print(f"\nInput feature shape: {features.shape}")
    try:
        predictions = model.predict(features)
    except Exception as error:
        raise RuntimeError(
            f"Prediction failed for input shape {features.shape}: {error}"
        ) from error

    actual_classes = None
    if "Label" in sample.columns:
        raw_labels = sample["Label"]
        unknown_labels = sorted(
            set(raw_labels.dropna().astype(str)) - set(ACTUAL_LABELS)
        )
        if raw_labels.isna().any() or unknown_labels:
            raise ValueError(
                "The matrix Label column must contain recognized labels "
                "('Normal'/'Anomaly' or HDFS 'Success'/'Fail'); "
                f"unknown values: {unknown_labels}, "
                f"missing values: {int(raw_labels.isna().sum())}."
            )
        actual_classes = raw_labels.astype(str).map(ACTUAL_LABELS)

    print("\nPredictions for the first 10 HDFS rows:")
    for row_index, prediction in enumerate(predictions):
        predicted_class = CLASS_NAMES.get(int(prediction), str(prediction))
        block_id = sample.iloc[row_index].get("BlockId", row_index)
        result = f"BlockId={block_id}: predicted={predicted_class}"
        if actual_classes is not None:
            actual_class = actual_classes.iloc[row_index]
            result += (
                f", actual={actual_class}, "
                f"correct={'Yes' if predicted_class == actual_class else 'No'}"
            )
        print(result)


if __name__ == "__main__":
    main()
