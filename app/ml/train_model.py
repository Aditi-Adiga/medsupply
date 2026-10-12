import json
import os
import sys
import time

# Ensure repository root in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app.ml.preprocessing import prepare_demand_data


DATASET_PATH = "data/medical_supply_20_medicines.csv"
MODEL_DIR = "app/ml/models"
MODEL_PATH = os.path.join(MODEL_DIR, "demand_forecaster.joblib")
METADATA_PATH = os.path.join(MODEL_DIR, "model_metadata.json")


def train_global_model():
    """Trains a comprehensive gradient boosted demand forecasting model across all 20 medicines and 10 hospitals."""
    print("=" * 60)
    print("TRAINING PRODUCTION MACHINE LEARNING MODEL")
    print("=" * 60)

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    os.makedirs(MODEL_DIR, exist_ok=True)

    print(f"1. Loading dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    print(f"   [OK] Loaded {len(df):,} historical medical records across {df['hospital_id'].nunique()} hospitals and {df['medicine_id'].nunique()} medicines.")

    print("2. Engineering time-series & clinical features...")
    t0 = time.time()
    
    # Process group by group to maintain clean time-series lags
    processed_groups = []
    for _, group in df.groupby(["hospital_id", "medicine_id"]):
        group_feat = prepare_demand_data(group)
        processed_groups.append(group_feat)
    
    full_df = pd.concat(processed_groups, ignore_index=True)
    print(f"   [OK] Feature engineering completed in {time.time() - t0:.2f}s.")

    # Select feature columns
    feature_cols = [
        "day_of_week",
        "is_weekend",
        "day_of_month",
        "month",
        "quarter",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_7",
        "lag_14",
        "rolling_mean_3",
        "rolling_mean_7",
        "rolling_mean_14",
        "rolling_std_7",
        "ema_7",
        "ema_14",
    ]

    if "patient_load" in full_df.columns:
        feature_cols.append("patient_load")
    if "emergency_demand" in full_df.columns:
        feature_cols.append("emergency_demand")

    X = full_df[feature_cols].fillna(0.0)
    y = full_df["units_consumed"].fillna(0.0)

    # Chronological Train-Test Split (80% Train, 20% Holdout Test)
    split_idx = int(len(full_df) * 0.80)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    print(f"3. Training Gradient Boosting Regressor on {len(X_train):,} training records...")
    t_train = time.time()
    model = GradientBoostingRegressor(
        n_estimators=100,
        learning_rate=0.08,
        max_depth=5,
        subsample=0.85,
        random_state=42,
    )
    model.fit(X_train, y_train)
    train_duration = round(time.time() - t_train, 2)
    print(f"   [OK] Model training finished in {train_duration}s.")

    # Evaluation on Holdout Test Set
    print("4. Evaluating model on holdout test set (20% split)...")
    y_pred = model.predict(X_test)
    y_pred = np.clip(y_pred, 0, None)

    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = float(r2_score(y_test, y_pred))
    
    total_actual = float(np.sum(y_test))
    wape = float(np.sum(np.abs(y_test - y_pred)) / total_actual * 100) if total_actual > 0 else 0.0
    accuracy_pct = round(100.0 - wape, 2)

    print("\n" + "-" * 50)
    print("MODEL EVALUATION PERFORMANCE METRICS")
    print("-" * 50)
    print(f"  * Mean Absolute Error (MAE):       {mae:.2f} units")
    print(f"  * Root Mean Squared Error (RMSE):  {rmse:.2f} units")
    print(f"  * WAPE Error Rate:                {wape:.2f}%")
    print(f"  * Overall Forecast Accuracy:       {accuracy_pct:.2f}%")
    print(f"  * R2 Score (Variance Explained):  {r2:.4f}")
    print("-" * 50 + "\n")

    # Save Model Artifact
    print(f"5. Saving trained model artifact to {MODEL_PATH}...")
    joblib.dump({
        "model": model,
        "feature_cols": feature_cols,
        "metrics": {
            "MAE": round(mae, 2),
            "RMSE": round(rmse, 2),
            "WAPE_percent": round(wape, 2),
            "accuracy_percent": accuracy_pct,
            "R2_Score": round(r2, 4),
        },
        "training_metadata": {
            "total_samples": len(full_df),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "num_features": len(feature_cols),
            "features": feature_cols,
            "trained_at": pd.Timestamp.now().isoformat(),
            "model_type": "GradientBoostingRegressor",
        }
    }, MODEL_PATH)

    # Save metadata JSON
    with open(METADATA_PATH, "w") as f:
        json.dump({
            "model_type": "GradientBoostingRegressor",
            "n_estimators": 100,
            "features": feature_cols,
            "metrics": {
                "MAE": round(mae, 2),
                "RMSE": round(rmse, 2),
                "accuracy_percent": accuracy_pct,
                "R2_Score": round(r2, 4),
            },
            "dataset_rows": len(full_df),
            "trained_at": pd.Timestamp.now().isoformat(),
        }, f, indent=2)

    print("[SUCCESS] Model training & artifact persistence complete!")
    return model, feature_cols


if __name__ == "__main__":
    train_global_model()
