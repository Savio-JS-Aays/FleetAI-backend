from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sqlalchemy.orm import Session

from app import models

FEATURES = (
    "coolant_temp_variance",
    "oil_pressure_dips",
    "battery_voltage_sag",
    "dtc_recurrence_rate",
    "harsh_braking_frequency",
    "overload_duty_share",
    "high_rpm_dwell_time",
    "short_trip_ratio",
    "idle_time_pct",
)


def _load_labeled_history(part_code: str, db: Session) -> tuple[pd.DataFrame, list]:
    telematics = pd.read_sql(db.query(models.Telematics).statement, db.bind)
    failures = db.query(models.JobCard).filter(models.JobCard.part_code == part_code).all()

    if telematics.empty or not failures:
        return pd.DataFrame(), failures

    telematics["week_start_date"] = pd.to_datetime(telematics["week_start_date"])
    failure_dates_by_vin = {}
    for failure in failures:
        failure_dates_by_vin.setdefault(failure.vin, []).append(
            pd.Timestamp(failure.failure_date)
        )

    def next_failure_date(row):
        future_dates = [
            failure_date
            for failure_date in failure_dates_by_vin.get(row.vin, [])
            if failure_date >= row.week_start_date
        ]
        return min(future_dates) if future_dates else pd.NaT

    telematics["failure_date"] = telematics.apply(next_failure_date, axis=1)
    telematics["has_future_failure"] = telematics["failure_date"].notna()
    # Observations after the last known failure cannot be labelled as healthy;
    # exclude them instead of leaking post-failure data into the negatives.
    telematics = telematics[
        telematics["has_future_failure"]
        | ~telematics["vin"].isin(failure_dates_by_vin)
    ].copy()
    telematics["days_to_fail"] = (
        telematics["failure_date"] - telematics["week_start_date"]
    ).dt.days
    telematics["label"] = telematics["days_to_fail"].between(0, 28).astype(int)
    return telematics, failures


def _fit_model(training: pd.DataFrame, selected_signals: list[str]):
    if training["label"].nunique() < 2:
        return None

    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(training[selected_signals], training["label"])
    return model


def _percentage(value: float) -> float:
    return round(value * 100, 2)


def calculate_backtest(part_code: str, selected_signals: list[str], db: Session) -> dict:
    normalized_part = part_code.strip().upper()
    normalized_signals = list(dict.fromkeys(signal.strip() for signal in selected_signals))
    invalid_signals = [signal for signal in normalized_signals if signal not in FEATURES]

    if invalid_signals:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "invalid_input",
            "reason": f"Unknown signals: {', '.join(invalid_signals)}",
        }

    if not normalized_signals:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": "At least one historical signal is required to evaluate a rule.",
        }

    history, failures = _load_labeled_history(normalized_part, db)
    if history.empty or not failures:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": f"No telematics and failure history is available for {normalized_part}.",
        }

    if history["label"].nunique() < 2 or history["vin"].nunique() < 2:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": f"Not enough positive and negative historical observations for {normalized_part}.",
        }

    groups = history["vin"]
    fold_count = min(5, groups.nunique())
    true_positives = false_positives = false_negatives = 0
    out_of_sample_predictions = []

    for train_indices, test_indices in GroupKFold(n_splits=fold_count).split(
        history, history["label"], groups
    ):
        training = history.iloc[train_indices]
        testing = history.iloc[test_indices]
        model = _fit_model(training, normalized_signals)
        if model is None:
            continue

        probabilities = model.predict_proba(testing[normalized_signals])[:, 1]
        predicted = probabilities >= 0.5
        actual = testing["label"].to_numpy(dtype=bool)
        true_positives += int(np.sum(predicted & actual))
        false_positives += int(np.sum(predicted & ~actual))
        false_negatives += int(np.sum(~predicted & actual))
        out_of_sample_predictions.append(
            testing[["vin", "week_start_date", "failure_date"]].assign(
                predicted=predicted
            )
        )

    denominator_precision = true_positives + false_positives
    precision = (
        true_positives / denominator_precision if denominator_precision else 0.0
    )
    oof_predictions = (
        pd.concat(out_of_sample_predictions, ignore_index=True)
        if out_of_sample_predictions
        else pd.DataFrame()
    )
    detected_failures = 0
    if not oof_predictions.empty:
        for failure in failures:
            failure_date = pd.Timestamp(failure.failure_date)
            failure_alerts = oof_predictions[
                (oof_predictions["vin"] == failure.vin)
                & (oof_predictions["week_start_date"] <= failure_date)
                & (oof_predictions["week_start_date"] >= failure_date - timedelta(days=28))
                & oof_predictions["predicted"]
            ]
            if not failure_alerts.empty:
                detected_failures += 1

    missed_failures = len(failures) - detected_failures
    coverage = (
        detected_failures / (detected_failures + missed_failures)
        if detected_failures + missed_failures
        else 0.0
    )

    full_model = _fit_model(history, normalized_signals)
    lead_times = []
    if full_model is not None:
        history["alert_probability"] = full_model.predict_proba(
            history[normalized_signals]
        )[:, 1]
        for failure in failures:
            observations = history[
                (history["vin"] == failure.vin)
                & (history["week_start_date"] <= pd.Timestamp(failure.failure_date))
                & (history["week_start_date"] >= pd.Timestamp(failure.failure_date) - timedelta(days=56))
            ].sort_values("week_start_date")
            alerts = observations[observations["alert_probability"] >= 0.5]
            if not alerts.empty:
                first_alert = alerts.iloc[0]["week_start_date"]
                lead_times.append((pd.Timestamp(failure.failure_date) - first_alert).days)

    return {
        "days_to_alert": round(float(np.mean(lead_times)), 2) if lead_times else None,
        "rule_precision_pct": _percentage(precision),
        "rule_coverage_pct": _percentage(coverage),
        "status": "ok",
        "evaluation": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "evaluated_failures": len(failures),
            "detected_failures": detected_failures,
            "missed_failures": missed_failures,
            "alert_lead_time_samples": len(lead_times),
            "selected_signals": normalized_signals,
        },
    }
