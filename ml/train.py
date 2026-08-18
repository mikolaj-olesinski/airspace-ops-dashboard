"""Train a LightGBM classifier for delayed_15min risk and log everything to MLflow.

Time-based train/test split (not random): train on everything before TEST_CUTOFF, test
on the holdout tail. This mirrors how the model would actually be used (predicting
future delays from past patterns) and avoids the rolling-window features leaking
information across a random split.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# MLflow 3.x deprecated the local filesystem tracking store in favor of a sqlite/db
# backend, but sqlite's URI-to-path resolution mishandles this repo's UNC path
# (\\wsl.localhost\...) on Windows. Opt back into the (still supported) file store.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

import lightgbm as lgb
import matplotlib.pyplot as plt
import mlflow
import mlflow.lightgbm
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN

FEATURES_PATH = "data/processed/features-00000-of-00001.parquet"
# MLflow 3.x defaults to a sqlite tracking store; its URI-to-path resolution mishandles
# this repo's UNC path (\\wsl.localhost\...) on Windows. Use the classic local file
# store instead (mlruns/, already gitignored) -- plain directory creation, no sqlite.
MLFLOW_TRACKING_URI = "file:./mlruns"
TEST_CUTOFF = "2025-09-01"  # last ~4 months held out as a time-based test set
CATEGORICAL_COLUMNS = ["adep", "typecode"]
MLFLOW_EXPERIMENT = "airspace-delay-risk"

PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "verbosity": -1,
}
NUM_BOOST_ROUND = 500
EARLY_STOPPING_ROUNDS = 30


def load_data() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES_PATH)
    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].astype("category")
    return df


def time_split(df: pd.DataFrame):
    train = df[df["first_seen"] < TEST_CUTOFF]
    test = df[df["first_seen"] >= TEST_CUTOFF]
    return train, test


def plot_feature_importance(model: lgb.Booster, path: str) -> None:
    importance = pd.Series(
        model.feature_importance(importance_type="gain"), index=model.feature_name()
    ).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    importance.plot(kind="barh", ax=ax)
    ax.set_xlabel("gain")
    ax.set_title("Feature importance - delayed_15min risk model")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    df = load_data()
    train, test = time_split(df)
    print(f"train: {len(train):,} rows ({train['first_seen'].min()} -> {train['first_seen'].max()})")
    print(f"test:  {len(test):,} rows ({test['first_seen'].min()} -> {test['first_seen'].max()})")

    X_train, y_train = train[FEATURE_COLUMNS], train[TARGET_COLUMN]
    X_test, y_test = test[FEATURE_COLUMNS], test[TARGET_COLUMN]

    params = dict(PARAMS)
    params["scale_pos_weight"] = (y_train == 0).sum() / (y_train == 1).sum()

    train_set = lgb.Dataset(X_train, label=y_train, categorical_feature=CATEGORICAL_COLUMNS)
    test_set = lgb.Dataset(
        X_test, label=y_test, categorical_feature=CATEGORICAL_COLUMNS, reference=train_set
    )

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    with mlflow.start_run():
        mlflow.log_params(params)
        mlflow.log_params(
            {
                "num_boost_round": NUM_BOOST_ROUND,
                "test_cutoff": TEST_CUTOFF,
                "n_train": len(train),
                "n_test": len(test),
            }
        )

        model = lgb.train(
            params,
            train_set,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[train_set, test_set],
            valid_names=["train", "test"],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING_ROUNDS),
                lgb.log_evaluation(50),
            ],
        )

        y_pred_proba = model.predict(X_test, num_iteration=model.best_iteration)
        y_pred = (y_pred_proba >= 0.5).astype(int)

        metrics = {
            "auc": roc_auc_score(y_test, y_pred_proba),
            "pr_auc": average_precision_score(y_test, y_pred_proba),
            "f1": f1_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall": recall_score(y_test, y_pred),
        }
        print("\n--- test metrics ---")
        for k, v in metrics.items():
            print(f"{k}: {v:.4f}")
        mlflow.log_metrics(metrics)
        mlflow.log_param("best_iteration", model.best_iteration)

        importance_path = "data/processed/_feature_importance.png"
        plot_feature_importance(model, importance_path)
        mlflow.log_artifact(importance_path)

        mlflow.lightgbm.log_model(model, artifact_path="model")
        print(f"\nMLflow run: {mlflow.active_run().info.run_id}")

    print("Done. Run `mlflow ui` in repo/ to inspect results.")


if __name__ == "__main__":
    main()
