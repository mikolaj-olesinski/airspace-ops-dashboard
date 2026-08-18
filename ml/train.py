"""Train a LightGBM classifier for delayed_15min risk and log everything to MLflow.

Three-way time-based split (not random, and not just train/test):
  - train_fit  (< VAL_CUTOFF)              -- fits each candidate model
  - val        (VAL_CUTOFF .. TEST_CUTOFF) -- early stopping + hyperparameter selection
                                               + picks the decision threshold
  - test       (>= TEST_CUTOFF)            -- touched exactly once, for the final report

Time-based (not random) because the rolling-window features would otherwise leak
across a random split, and because this mirrors real deployment: predicting future
delays from past patterns. A separate validation set (rather than the original
baseline's train/test-only split) matters here specifically because early stopping and
hyperparameter choice both make decisions FROM data -- letting those decisions watch
the test set would quietly bias the "final" test metrics.

A small hyperparameter search runs as nested MLflow child runs under a "hyperparam_
search" parent; the winning config (by validation PR-AUC, more informative than AUC
given the ~5% positive rate) is refit on all pre-test data and logged as "final_model".
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
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN

FEATURES_PATH = "data/processed/features-00000-of-00001.parquet"
MLFLOW_TRACKING_URI = "file:./mlruns"
MLFLOW_EXPERIMENT = "airspace-delay-risk"

VAL_CUTOFF = "2025-06-01"   # last ~3 months before TEST_CUTOFF held out for tuning
TEST_CUTOFF = "2025-09-01"  # last ~4 months held out as the final, untouched test set
CATEGORICAL_COLUMNS = ["adep", "typecode"]

BASE_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "verbosity": -1,
}
NUM_BOOST_ROUND = 500
EARLY_STOPPING_ROUNDS = 30

# a handful of hand-picked candidates rather than a full grid, to keep the search
# fast: two vary tree structure, one varies how hard the class-imbalance weight pushes
# recall vs precision.
SEARCH_SPACE = [
    {"num_leaves": 31, "learning_rate": 0.05, "min_data_in_leaf": 100, "pos_weight_mult": 1.0},
    {"num_leaves": 63, "learning_rate": 0.05, "min_data_in_leaf": 100, "pos_weight_mult": 1.0},
    {"num_leaves": 15, "learning_rate": 0.05, "min_data_in_leaf": 300, "pos_weight_mult": 1.0},
    {"num_leaves": 31, "learning_rate": 0.05, "min_data_in_leaf": 100, "pos_weight_mult": 0.5},
]


def load_data() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES_PATH)
    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].astype("category")
    return df


def three_way_split(df: pd.DataFrame):
    train_fit = df[df["first_seen"] < VAL_CUTOFF]
    val = df[(df["first_seen"] >= VAL_CUTOFF) & (df["first_seen"] < TEST_CUTOFF)]
    test = df[df["first_seen"] >= TEST_CUTOFF]
    return train_fit, val, test


def make_dataset(df: pd.DataFrame, reference=None) -> lgb.Dataset:
    return lgb.Dataset(
        df[FEATURE_COLUMNS], label=df[TARGET_COLUMN],
        categorical_feature=CATEGORICAL_COLUMNS, reference=reference,
    )


def best_threshold_by_f1(y_true, y_proba):
    precision, recall, thresholds = precision_recall_curve(y_true, y_proba)
    f1 = 2 * precision * recall / (precision + recall + 1e-12)
    best_idx = f1[:-1].argmax()  # thresholds has one fewer entry than precision/recall
    return float(thresholds[best_idx]), float(f1[best_idx])


def plot_pr_curve(y_true, y_proba, path: str) -> None:
    precision, recall, _ = precision_recall_curve(y_true, y_proba)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(recall, precision)
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title("Precision-recall curve (test)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


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


def run_search(train_fit: pd.DataFrame, val: pd.DataFrame):
    base_pos_weight = (train_fit[TARGET_COLUMN] == 0).sum() / (train_fit[TARGET_COLUMN] == 1).sum()
    train_set = make_dataset(train_fit)
    val_set = make_dataset(val, reference=train_set)
    y_val = val[TARGET_COLUMN]

    results = []
    with mlflow.start_run(run_name="hyperparam_search"):
        for i, cfg in enumerate(SEARCH_SPACE):
            params = dict(BASE_PARAMS)
            params["num_leaves"] = cfg["num_leaves"]
            params["learning_rate"] = cfg["learning_rate"]
            params["min_data_in_leaf"] = cfg["min_data_in_leaf"]
            params["scale_pos_weight"] = base_pos_weight * cfg["pos_weight_mult"]

            with mlflow.start_run(run_name=f"trial_{i}", nested=True):
                mlflow.log_params({**params, "pos_weight_mult": cfg["pos_weight_mult"]})
                model = lgb.train(
                    params,
                    train_set,
                    num_boost_round=NUM_BOOST_ROUND,
                    valid_sets=[val_set],
                    valid_names=["val"],
                    callbacks=[
                        lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                        lgb.log_evaluation(0),
                    ],
                )
                y_val_proba = model.predict(val[FEATURE_COLUMNS], num_iteration=model.best_iteration)
                val_auc = roc_auc_score(y_val, y_val_proba)
                val_pr_auc = average_precision_score(y_val, y_val_proba)
                mlflow.log_metrics({"val_auc": val_auc, "val_pr_auc": val_pr_auc})
                mlflow.log_param("best_iteration", model.best_iteration)

                print(
                    f"trial {i}: {cfg} -> val_auc={val_auc:.4f} "
                    f"val_pr_auc={val_pr_auc:.4f} (best_iter={model.best_iteration})"
                )
                results.append(
                    {
                        "cfg": cfg,
                        "params": params,
                        "val_auc": val_auc,
                        "val_pr_auc": val_pr_auc,
                        "best_iteration": model.best_iteration,
                    }
                )

        best = max(results, key=lambda r: r["val_pr_auc"])
        mlflow.log_param("chosen_trial_cfg", str(best["cfg"]))
        mlflow.log_metric("chosen_val_pr_auc", best["val_pr_auc"])

    print(f"\nbest config: {best['cfg']} (val_pr_auc={best['val_pr_auc']:.4f})")
    return best


def main():
    df = load_data()
    train_fit, val, test = three_way_split(df)
    print(f"train_fit: {len(train_fit):,} rows (< {VAL_CUTOFF})")
    print(f"val:       {len(val):,} rows ({VAL_CUTOFF} -> {TEST_CUTOFF})")
    print(f"test:      {len(test):,} rows (>= {TEST_CUTOFF})")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    best = run_search(train_fit, val)

    # --- final refit on all pre-test data (train_fit + val), evaluated once on the
    # untouched test set, using the winning hyperparameters and round count from search
    train_final = df[df["first_seen"] < TEST_CUTOFF]
    train_final_set = make_dataset(train_final)

    with mlflow.start_run(run_name="final_model"):
        mlflow.log_params(best["params"])
        mlflow.log_params(
            {
                "num_boost_round": best["best_iteration"],
                "val_cutoff": VAL_CUTOFF,
                "test_cutoff": TEST_CUTOFF,
                "n_train_final": len(train_final),
                "n_test": len(test),
            }
        )

        final_model = lgb.train(best["params"], train_final_set, num_boost_round=best["best_iteration"])

        # threshold picked from validation (re-scored by the final model), never from test
        y_val_proba = final_model.predict(val[FEATURE_COLUMNS])
        threshold, val_f1 = best_threshold_by_f1(val[TARGET_COLUMN], y_val_proba)
        mlflow.log_param("decision_threshold", threshold)
        print(f"\ndecision threshold (best F1 on val): {threshold:.4f} (val_f1={val_f1:.4f})")

        y_test = test[TARGET_COLUMN]
        y_test_proba = final_model.predict(test[FEATURE_COLUMNS])
        y_test_pred = (y_test_proba >= threshold).astype(int)

        metrics = {
            "auc": roc_auc_score(y_test, y_test_proba),
            "pr_auc": average_precision_score(y_test, y_test_proba),
            "f1": f1_score(y_test, y_test_pred),
            "precision": precision_score(y_test, y_test_pred),
            "recall": recall_score(y_test, y_test_pred),
        }
        print("\n--- final test metrics ---")
        for k, v in metrics.items():
            print(f"{k}: {v:.4f}")
        mlflow.log_metrics(metrics)

        test_eval = test[["adep", TARGET_COLUMN]].copy()
        test_eval["proba"] = y_test_proba
        per_airport = test_eval.groupby("adep", observed=True).apply(
            lambda g: pd.Series(
                {
                    "n": len(g),
                    "actual_rate": g[TARGET_COLUMN].mean(),
                    "mean_predicted_proba": g["proba"].mean(),
                    "auc": roc_auc_score(g[TARGET_COLUMN], g["proba"])
                    if g[TARGET_COLUMN].nunique() > 1
                    else float("nan"),
                }
            ),
            include_groups=False,
        )
        print("\n--- per-airport test breakdown ---")
        print(per_airport)
        per_airport_path = "data/processed/_per_airport_eval.csv"
        per_airport.to_csv(per_airport_path)
        mlflow.log_artifact(per_airport_path)

        pr_curve_path = "data/processed/_pr_curve.png"
        plot_pr_curve(y_test, y_test_proba, pr_curve_path)
        mlflow.log_artifact(pr_curve_path)

        importance_path = "data/processed/_feature_importance.png"
        plot_feature_importance(final_model, importance_path)
        mlflow.log_artifact(importance_path)

        mlflow.lightgbm.log_model(final_model, name="model")
        print(f"\nMLflow run: {mlflow.active_run().info.run_id}")

    print("Done. Run `mlflow ui` in repo/ to inspect results.")


if __name__ == "__main__":
    main()
