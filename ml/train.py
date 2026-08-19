"""Train a LightGBM classifier for delayed_15min risk and log everything to MLflow.

Time-based (not random) split, in two parts:
  - pre-test  (< TEST_CUTOFF)   -- everything hyperparameter selection is allowed to see
  - test      (>= TEST_CUTOFF)  -- touched exactly once, for the final report

Time-based because the rolling-window features would otherwise leak across a random
split, and because this mirrors real deployment: predicting future delays from past
patterns.

Hyperparameter selection uses walk-forward (rolling-origin) cross-validation instead of
a single static validation window: N_FOLDS consecutive FOLD_MONTHS-wide validation
windows, each fold trained on an expanding window of everything before it and validated
on the window right after -- e.g. train on 2023-01..2024-09, validate on 2024-09..12;
train on 2023-01..2024-12, validate on 2025-01..03; and so on, ending with the fold
right before TEST_CUTOFF. A single validation window risks picking hyperparameters that
just happen to fit one arbitrary period's weather/seasonality; averaging PR-AUC across
several rolling windows is a more honest estimate of how a config generalizes forward in
time. This still never touches the held-out test set -- all folds live inside pre-test
data, same as the original single-split design.

A small hyperparameter search runs as nested MLflow child runs under a "hyperparam_
search_cv" parent; the winning config (by mean validation PR-AUC across folds, more
informative than AUC given the ~5% positive rate) is refit on all pre-test data and
logged as "final_model". The decision threshold is picked from the single most recent
fold (the one immediately preceding TEST_CUTOFF) -- the most representative stand-in for
"what's about to happen" without touching the actual test set.
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
import numpy as np
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

TEST_CUTOFF = "2025-09-01"  # everything from here on is the final, untouched test set
CATEGORICAL_COLUMNS = ["adep", "typecode"]

# walk-forward CV: N_FOLDS rolling validation windows of FOLD_MONTHS each, working
# backward from TEST_CUTOFF -- see the module docstring
N_FOLDS = 4
FOLD_MONTHS = 3

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


def rolling_fold_cutoffs(final_val_end: str, months: int, n_folds: int) -> list[tuple[str, str]]:
    """n_folds consecutive [start, end) validation windows of `months` width, working
    backward from final_val_end, oldest first. Each fold's implicit training set is
    "everything before its own start" (expanding window) -- computed by the caller, not
    here, since building it just needs the start date."""
    end = pd.Timestamp(final_val_end)
    cuts = []
    for _ in range(n_folds):
        start = end - pd.DateOffset(months=months)
        cuts.append((start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        end = start
    return list(reversed(cuts))


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


def run_search_cv(df: pd.DataFrame, fold_cutoffs: list[tuple[str, str]]):
    """Walk-forward hyperparameter search: each candidate config is fit and scored on
    every rolling fold, then ranked by its mean validation PR-AUC across folds (not a
    single fold's score) -- see module docstring for why."""
    results = []
    with mlflow.start_run(run_name="hyperparam_search_cv"):
        mlflow.log_param("n_folds", len(fold_cutoffs))
        mlflow.log_param("fold_cutoffs", str(fold_cutoffs))

        for i, cfg in enumerate(SEARCH_SPACE):
            with mlflow.start_run(run_name=f"trial_{i}", nested=True):
                mlflow.log_params({**cfg})
                fold_aucs, fold_pr_aucs, fold_iters = [], [], []

                for fold_i, (val_start, val_end) in enumerate(fold_cutoffs):
                    train_fold = df[df["first_seen"] < val_start]
                    val_fold = df[(df["first_seen"] >= val_start) & (df["first_seen"] < val_end)]

                    base_pos_weight = (
                        (train_fold[TARGET_COLUMN] == 0).sum() / (train_fold[TARGET_COLUMN] == 1).sum()
                    )
                    params = dict(BASE_PARAMS)
                    params["num_leaves"] = cfg["num_leaves"]
                    params["learning_rate"] = cfg["learning_rate"]
                    params["min_data_in_leaf"] = cfg["min_data_in_leaf"]
                    params["scale_pos_weight"] = base_pos_weight * cfg["pos_weight_mult"]

                    train_set = make_dataset(train_fold)
                    val_set = make_dataset(val_fold, reference=train_set)
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
                    y_val_proba = model.predict(val_fold[FEATURE_COLUMNS], num_iteration=model.best_iteration)
                    fold_auc = roc_auc_score(val_fold[TARGET_COLUMN], y_val_proba)
                    fold_pr_auc = average_precision_score(val_fold[TARGET_COLUMN], y_val_proba)
                    mlflow.log_metrics(
                        {f"fold{fold_i}_val_auc": fold_auc, f"fold{fold_i}_val_pr_auc": fold_pr_auc}
                    )
                    fold_aucs.append(fold_auc)
                    fold_pr_aucs.append(fold_pr_auc)
                    fold_iters.append(model.best_iteration)

                mean_auc, std_auc = float(np.mean(fold_aucs)), float(np.std(fold_aucs))
                mean_pr_auc, std_pr_auc = float(np.mean(fold_pr_aucs)), float(np.std(fold_pr_aucs))
                mean_iter = int(round(np.mean(fold_iters)))
                mlflow.log_metrics(
                    {
                        "val_auc_mean": mean_auc,
                        "val_auc_std": std_auc,
                        "val_pr_auc_mean": mean_pr_auc,
                        "val_pr_auc_std": std_pr_auc,
                        "best_iteration_mean": mean_iter,
                    }
                )

                print(
                    f"trial {i}: {cfg} -> val_pr_auc={mean_pr_auc:.4f} +/- {std_pr_auc:.4f} "
                    f"(val_auc={mean_auc:.4f} +/- {std_auc:.4f}, over {len(fold_cutoffs)} folds, "
                    f"mean_best_iter={mean_iter})"
                )
                results.append(
                    {
                        "cfg": cfg,
                        "val_auc": mean_auc,
                        "val_pr_auc": mean_pr_auc,
                        "val_pr_auc_std": std_pr_auc,
                        "best_iteration": mean_iter,
                    }
                )

        best = max(results, key=lambda r: r["val_pr_auc"])
        mlflow.log_param("chosen_trial_cfg", str(best["cfg"]))
        mlflow.log_metric("chosen_val_pr_auc_mean", best["val_pr_auc"])
        mlflow.log_metric("chosen_val_pr_auc_std", best["val_pr_auc_std"])

    print(f"\nbest config: {best['cfg']} (val_pr_auc={best['val_pr_auc']:.4f} +/- {best['val_pr_auc_std']:.4f})")
    return best


def main():
    df = load_data()
    test = df[df["first_seen"] >= TEST_CUTOFF]
    fold_cutoffs = rolling_fold_cutoffs(TEST_CUTOFF, FOLD_MONTHS, N_FOLDS)

    print(f"walk-forward folds ({N_FOLDS} x {FOLD_MONTHS} months, expanding training window):")
    for val_start, val_end in fold_cutoffs:
        n_train = (df["first_seen"] < val_start).sum()
        n_val = ((df["first_seen"] >= val_start) & (df["first_seen"] < val_end)).sum()
        print(f"  train < {val_start}: {n_train:,} rows | val {val_start} -> {val_end}: {n_val:,} rows")
    print(f"test:      {len(test):,} rows (>= {TEST_CUTOFF}, untouched until the very end)")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    best = run_search_cv(df, fold_cutoffs)

    # --- final refit on all pre-test data, evaluated once on the untouched test set,
    # using the winning hyperparameters and mean round count from the CV folds
    train_final = df[df["first_seen"] < TEST_CUTOFF]
    train_final_set = make_dataset(train_final)
    base_pos_weight = (train_final[TARGET_COLUMN] == 0).sum() / (train_final[TARGET_COLUMN] == 1).sum()
    final_params = dict(BASE_PARAMS)
    final_params["num_leaves"] = best["cfg"]["num_leaves"]
    final_params["learning_rate"] = best["cfg"]["learning_rate"]
    final_params["min_data_in_leaf"] = best["cfg"]["min_data_in_leaf"]
    final_params["scale_pos_weight"] = base_pos_weight * best["cfg"]["pos_weight_mult"]

    # most recent fold, right before TEST_CUTOFF -- the closest honest stand-in for
    # "what's about to happen" without touching the actual held-out test set
    thresh_start, thresh_end = fold_cutoffs[-1]
    threshold_val = df[(df["first_seen"] >= thresh_start) & (df["first_seen"] < thresh_end)]

    with mlflow.start_run(run_name="final_model"):
        mlflow.log_params(final_params)
        mlflow.log_params(
            {
                "num_boost_round": best["best_iteration"],
                "n_folds": N_FOLDS,
                "fold_months": FOLD_MONTHS,
                "test_cutoff": TEST_CUTOFF,
                "n_train_final": len(train_final),
                "n_test": len(test),
            }
        )

        final_model = lgb.train(final_params, train_final_set, num_boost_round=best["best_iteration"])

        # threshold picked from the most recent fold (re-scored by the final model),
        # never from test
        y_val_proba = final_model.predict(threshold_val[FEATURE_COLUMNS])
        threshold, val_f1 = best_threshold_by_f1(threshold_val[TARGET_COLUMN], y_val_proba)
        mlflow.log_param("decision_threshold", threshold)
        print(f"\ndecision threshold (best F1 on most recent fold): {threshold:.4f} (val_f1={val_f1:.4f})")

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
