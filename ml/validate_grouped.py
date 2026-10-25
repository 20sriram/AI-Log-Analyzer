from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedGroupKFold


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data" / "hdfs" / "preprocessed"
MODEL_DIR = PROJECT_DIR / "ml" / "models"
MODEL_PATH = MODEL_DIR / "hdfs_random_forest_grouped.joblib"
TEST_SIZE = 0.20
N_SPLITS = 5

CLASS_NAMES = {0: "Normal", 1: "Anomaly"}
LABEL_VALUES = {"Normal": 0, "Anomaly": 1}


def main() -> None:
    """Train and evaluate a model with identical event patterns kept together."""
    matrix_path = DATA_DIR / "Event_occurrence_matrix.csv"
    labels_path = DATA_DIR / "anomaly_label.csv"

    if not matrix_path.is_file():
        raise FileNotFoundError(f"Event-occurrence matrix not found: {matrix_path}")
    if not labels_path.is_file():
        raise FileNotFoundError(f"Anomaly labels not found: {labels_path}")

    matrix = pd.read_csv(matrix_path)
    labels = pd.read_csv(labels_path)

    for name, frame, required_columns, source_path in (
        ("event-occurrence matrix", matrix, {"BlockId"}, matrix_path),
        ("anomaly labels", labels, {"BlockId", "Label"}, labels_path),
    ):
        missing = required_columns.difference(frame.columns)
        if missing:
            raise ValueError(
                f"{source_path} is missing required column(s): "
                f"{', '.join(sorted(missing))}"
            )
        if frame["BlockId"].isna().any():
            raise ValueError(f"{source_path} contains missing BlockId values.")
        if frame["BlockId"].duplicated().any():
            duplicates = frame.loc[frame["BlockId"].duplicated(), "BlockId"].head(5)
            raise ValueError(
                f"{name} contains duplicate BlockId values, for example: "
                f"{duplicates.tolist()}"
            )

    # Validate exact key coverage before reindexing, so no rows silently disappear.
    matrix_ids = pd.Index(matrix["BlockId"])
    label_ids = pd.Index(labels["BlockId"])
    missing_labels = matrix_ids.difference(label_ids)
    extra_labels = label_ids.difference(matrix_ids)
    if len(missing_labels) or len(extra_labels):
        details = []
        if len(missing_labels):
            details.append(f"{len(missing_labels)} matrix BlockId(s) lack labels")
        if len(extra_labels):
            details.append(f"{len(extra_labels)} label BlockId(s) lack matrix rows")
        raise ValueError(
            "BlockId mismatch between the event matrix and anomaly labels: "
            + "; ".join(details)
        )

    feature_columns = [
        column
        for column in matrix.columns
        if column.startswith("E") and column[1:].isdigit()
    ]
    if not feature_columns:
        raise ValueError(
            f"No event-count features named E1, E2, ... were found in {matrix_path}."
        )

    try:
        features = matrix[feature_columns].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Event-count features must contain only numeric values."
        ) from error
    if features.isna().any().any():
        raise ValueError("Event-count features contain missing values.")

    # Remove features that cannot help distinguish samples (for example, E22).
    constant_features = [
        column for column in features.columns if features[column].nunique() <= 1
    ]
    features = features.drop(columns=constant_features)
    if features.empty:
        raise ValueError("No non-constant event-count features remain.")

    aligned_labels = labels.set_index("BlockId")["Label"].reindex(matrix_ids)
    invalid_mask = aligned_labels.isna() | ~aligned_labels.isin(LABEL_VALUES)
    if invalid_mask.any():
        invalid_values = aligned_labels[invalid_mask].dropna().unique()
        invalid_block_ids = matrix_ids[invalid_mask.to_numpy()][:5].tolist()
        raise ValueError(
            "Labels must be exactly 'Normal' or 'Anomaly'; "
            f"found invalid value(s) {invalid_values.tolist()} and "
            f"{int(aligned_labels.isna().sum())} missing value(s). "
            f"Example affected BlockId(s): {invalid_block_ids}"
        )
    targets = aligned_labels.map(LABEL_VALUES).astype("int8")

    if targets.nunique() != 2:
        raise ValueError(
            "Grouped validation requires both Normal and Anomaly labels in the "
            "complete dataset."
        )

    # Factorization assigns the same group ID only to identical feature rows.
    groups = pd.MultiIndex.from_frame(features).factorize(sort=False)[0]
    group_count = int(groups.max()) + 1
    if group_count < N_SPLITS:
        raise ValueError(
            f"Grouped stratification needs at least {N_SPLITS} distinct feature "
            f"patterns; found {group_count}."
        )

    splitter = StratifiedGroupKFold(
        n_splits=N_SPLITS,
        shuffle=True,
        random_state=42,
    )
    try:
        candidate_splits = list(splitter.split(features, targets, groups))
    except ValueError as error:
        raise ValueError(
            "Stratified grouped splitting failed; no random-split fallback was "
            f"attempted. Check the class counts and grouped patterns. Details: {error}"
        ) from error

    overall_proportions = targets.value_counts(normalize=True)
    valid_candidates = []
    for train_indices, test_indices in candidate_splits:
        train_targets = targets.iloc[train_indices]
        test_targets = targets.iloc[test_indices]
        if train_targets.nunique() != 2 or test_targets.nunique() != 2:
            continue

        test_proportions = test_targets.value_counts(normalize=True)
        class_balance_error = sum(
            abs(
                test_proportions.get(class_id, 0.0)
                - overall_proportions.get(class_id, 0.0)
            )
            for class_id in (0, 1)
        )
        size_error = abs(len(test_indices) / len(features) - TEST_SIZE)
        valid_candidates.append(
            (
                (class_balance_error + size_error, class_balance_error, size_error),
                train_indices,
                test_indices,
            )
        )

    if not valid_candidates:
        raise ValueError(
            "StratifiedGroupKFold could not produce a split with both classes in "
            "both training and testing partitions. No random-split fallback was "
            "attempted."
        )

    _, train_indices, test_indices = min(valid_candidates, key=lambda item: item[0])
    X_train = features.iloc[train_indices]
    X_test = features.iloc[test_indices]
    y_train = targets.iloc[train_indices]
    y_test = targets.iloc[test_indices]
    train_groups = set(groups[train_indices])
    test_groups = set(groups[test_indices])
    shared_patterns = len(train_groups.intersection(test_groups))
    if shared_patterns:
        raise RuntimeError(
            "Grouped split integrity check failed: identical feature patterns "
            f"appear in both partitions ({shared_patterns} shared pattern(s))."
        )

    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test,
        predictions,
        labels=[0, 1],
        zero_division=0,
    )
    matrix_confusion = confusion_matrix(y_test, predictions, labels=[0, 1])

    print(f"Training rows: {len(X_train)}")
    print(f"Testing rows: {len(X_test)}")
    print(f"Features used: {features.shape[1]}")
    print(f"Constant features excluded: {constant_features or 'None'}")
    print(f"Shared feature patterns: {shared_patterns}")
    for split_name, split_targets in (("Training", y_train), ("Testing", y_test)):
        counts = split_targets.value_counts()
        print(
            f"{split_name} counts: "
            f"Normal={counts.get(0, 0)}, Anomaly={counts.get(1, 0)}"
        )

    print(f"Accuracy: {accuracy_score(y_test, predictions):.4f}")
    print(f"Balanced accuracy: {balanced_accuracy_score(y_test, predictions):.4f}")
    print("\nPer-class metrics:")
    for index, class_id in enumerate((0, 1)):
        print(
            f"{CLASS_NAMES[class_id]}: "
            f"precision={precision[index]:.4f}, "
            f"recall={recall[index]:.4f}, "
            f"F1-score={f1[index]:.4f}"
        )
    print("\nConfusion matrix (rows=actual, columns=predicted; order=Normal, Anomaly):")
    print(matrix_confusion)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\nGrouped-validation model saved to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
