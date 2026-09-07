from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "backend" / "app_data"
MODEL_PATH = DATA_DIR / "trained_flood_model.joblib"
METADATA_PATH = DATA_DIR / "ml_model_metadata.json"

FEATURES = [
    "rainfall_mm_hr",
    "slope_percent",
    "flow_accumulation",
    "imperviousness",
    "drainage_capacity",
    "drainage_utilization",
    "blockage_factor",
]

RANDOM_SEED = 42
SAMPLE_COUNT = 6000


def sigmoid(value):
    return 1 / (1 + np.exp(-value))


def create_synthetic_training_data(n_samples=SAMPLE_COUNT):
    """
    Generates transparent, physically motivated prototype data.

    The target probability is derived from rainfall/runoff/drainage pressure,
    then small noise is added so the ML model learns realistic variation
    rather than merely memorising a single hard-coded rule.
    """
    rng = np.random.default_rng(RANDOM_SEED)

    rainfall = rng.uniform(5, 100, n_samples)
    slope = rng.uniform(0.2, 8.0, n_samples)
    flow_accumulation = rng.uniform(0.1, 1.0, n_samples)
    imperviousness = rng.uniform(0.45, 0.9, n_samples)
    drainage_capacity = rng.uniform(35, 100, n_samples)
    blockage_factor = rng.uniform(0.0, 0.35, n_samples)

    terrain_multiplier = (
        0.85
        + (slope / 100) * 1.5
        + flow_accumulation * 0.45
    )

    runoff = rainfall * imperviousness * terrain_multiplier
    effective_capacity = drainage_capacity * (1 - blockage_factor)
    drainage_utilization = runoff / effective_capacity

    # Physics-informed synthetic flood probability.
    # Rainfall/runoff and overloaded/blocked drainage raise flood likelihood.
    flood_pressure = (
        (drainage_utilization - 0.65) * 3.5
        + (flow_accumulation - 0.45) * 1.1
        + (slope - 3.0) * 0.05
        + blockage_factor * 1.4
    )

    probability = sigmoid(flood_pressure)

    # Small uncertainty models local conditions not represented in this MVP.
    probability += rng.normal(0, 0.035, n_samples)
    probability = np.clip(probability, 0.02, 0.98)

    return pd.DataFrame({
        "rainfall_mm_hr": rainfall,
        "slope_percent": slope,
        "flow_accumulation": flow_accumulation,
        "imperviousness": imperviousness,
        "drainage_capacity": drainage_capacity,
        "drainage_utilization": drainage_utilization,
        "blockage_factor": blockage_factor,
        "flood_probability": probability,
    })


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = create_synthetic_training_data()
    X = data[FEATURES]
    y = data["flood_probability"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED
    )

    model = RandomForestRegressor(
        n_estimators=250,
        max_depth=14,
        min_samples_leaf=3,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "model_type": "RandomForestRegressor",
        },
        MODEL_PATH,
    )

    metadata = {
        "model_type": "RandomForestRegressor",
        "training_data": "Synthetic, physics-informed prototype data",
        "samples": SAMPLE_COUNT,
        "test_mae": round(float(mae), 4),
        "test_r2": round(float(r2), 4),
        "features": FEATURES,
        "purpose": (
            "Flood probability refinement. This model complements the "
            "rainfall-runoff and drainage physics model; it does not replace it."
        ),
    }

    with open(METADATA_PATH, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

    print("Model trained successfully.")
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved metadata: {METADATA_PATH}")
    print(f"Hold-out MAE: {mae:.4f}")
    print(f"Hold-out R²:  {r2:.4f}")


if __name__ == "__main__":
    main()