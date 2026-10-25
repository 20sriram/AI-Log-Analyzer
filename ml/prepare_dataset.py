
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

# Locate the dataset folder
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data" / "hdfs" / "preprocessed"
OUTPUT_DIR = PROJECT_DIR / "data" / "hdfs" / "prepared"

# Create the output folder
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load the event-count features and anomaly labels
matrix = pd.read_csv(DATA_DIR / "Event_occurrence_matrix.csv")
labels = pd.read_csv(DATA_DIR / "anomaly_label.csv")

# Select event-count columns only: E1, E2, ... E29
feature_columns = [
    column for column in matrix.columns
    if column.startswith("E") and column[1:].isdigit()
]

X = matrix[feature_columns].apply(pd.to_numeric, errors="raise")

# Match labels by BlockId
data = matrix[["BlockId"]].join(
    labels.set_index("BlockId"),
    on="BlockId",
    validate="one_to_one"
)

# Convert the labels to numeric targets
y = data["Label"].map({
    "Normal": 0,
    "Anomaly": 1
})

# Stop if any label is missing or unexpected
if y.isna().any():
    raise ValueError("Found missing or unexpected anomaly labels.")

if len(X) != len(y):
    raise ValueError("Feature and label row counts do not match.")

# Split data while preserving the class proportions
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y
)

# Save the prepared data
X_train.to_csv(OUTPUT_DIR / "X_train.csv", index=False)
X_test.to_csv(OUTPUT_DIR / "X_test.csv", index=False)
y_train.to_csv(OUTPUT_DIR / "y_train.csv", index=False, header=["Anomaly"])
y_test.to_csv(OUTPUT_DIR / "y_test.csv", index=False, header=["Anomaly"])

print("Dataset preparation completed!")
print("Number of features:", len(feature_columns))
print("Training rows:", len(X_train))
print("Testing rows:", len(X_test))

print("\nTraining labels:")
print(y_train.value_counts().rename(index={0: "Normal", 1: "Anomaly"}))

print("\nTesting labels:")
print(y_test.value_counts().rename(index={0: "Normal", 1: "Anomaly"}))

print("\nPrepared files saved to:", OUTPUT_DIR)
