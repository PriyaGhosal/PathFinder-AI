"""
Optional TensorFlow trainer for PathFinder-AI.

The Flask app uses an explainable recommender so it can run on any laptop.
Use this script when you want to train a neural classifier from a CSV dataset.
Expected CSV columns:
academic_stream, subjects, interests, skills, work_style, career_id

List columns can use comma-separated values, for example:
"Computer Science","Mathematics,Computer Science","Technology,Data","Python,Data Analysis","Analytical","data-scientist"
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer


BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / "data" / "career_training_data.csv"
MODEL_PATH = BASE_DIR / "model" / "career_model.keras"
METADATA_PATH = BASE_DIR / "model" / "model_metadata.json"


def split_values(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def build_features(df: pd.DataFrame):
    feature_parts = []
    metadata = {}

    for column in ["academic_stream", "subjects", "interests", "skills", "work_style"]:
        encoder = MultiLabelBinarizer()
        values = df[column].apply(split_values)
        encoded = encoder.fit_transform(values)
        feature_parts.append(encoded)
        metadata[column] = list(encoder.classes_)

    features = tf.concat([tf.constant(part, dtype=tf.float32) for part in feature_parts], axis=1)

    label_encoder = MultiLabelBinarizer()
    labels = label_encoder.fit_transform(df["career_id"].apply(lambda item: [item]))
    metadata["career_labels"] = list(label_encoder.classes_)

    return features.numpy(), labels, metadata


def main() -> None:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Create training data first: {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)
    x, y, metadata = build_features(df)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(x_train.shape[1],)),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(y_train.shape[1], activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    model.fit(x_train, y_train, validation_data=(x_test, y_test), epochs=40, batch_size=16)

    model.save(MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
