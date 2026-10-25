
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    balanced_accuracy_score
)

# Project folders
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data" / "hdfs" / "prepared"
MODEL_DIR = PROJECT_DIR / "ml" / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Load training and testing data
X_train = pd.read_csv(DATA_DIR / "X_train.csv")
X_test = pd.read_csv(DATA_DIR / "X_test.csv")
y_train = pd.read_csv(DATA_DIR / "y_train.csv")["Anomaly"]
y_test = pd.read_csv(DATA_DIR / "y_test.csv")["Anomaly"]

print("Training samples:", len(X_train))
print("Testing samples:", len(X_test))
print("Features:", len(X_train.columns))

# Create the class-weighted model
model = RandomForestClassifier(
    n_estimators=100,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

# Train the model
print("\nTraining model...")
model.fit(X_train, y_train)

# Evaluate on unseen test data
print("Evaluating model...")
predictions = model.predict(X_test)

print("\nAccuracy:", round(accuracy_score(y_test, predictions), 4))
print(
    "Balanced accuracy:",
    round(balanced_accuracy_score(y_test, predictions), 4)
)

print("\nClassification report:")
print(
    classification_report(
        y_test,
        predictions,
        labels=[0, 1],
        target_names=["Normal", "Anomaly"],
        zero_division=0
    )
)

print("Confusion matrix:")
print("Rows = actual; columns = predicted")
print(confusion_matrix(y_test, predictions, labels=[0, 1]))

# Save the trained model
model_path = MODEL_DIR / "hdfs_random_forest.joblib"
joblib.dump(model, model_path)

print("\nModel saved to:", model_path)
print("Training and evaluation completed!")
