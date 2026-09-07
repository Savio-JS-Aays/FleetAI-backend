from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
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

# A lower, explicit operating point is appropriate for an alerting rule.
# It remains high enough to avoid treating every low-confidence prediction
# as an alert, while allowing a useful pre-failure signal to be surfaced.
ALERT_THRESHOLD = 0.35
FAILURE_WINDOW_DAYS = 14


def _load_labeled_history(
    part_code: str,
    db: Session,
) -> tuple[pd.DataFrame, list]:

    telematics = pd.read_sql(
        db.query(models.Telematics).statement,
        db.bind,
    )

    failures = (
        db.query(models.JobCard)
        .filter(models.JobCard.part_code == part_code)
        .all()
    )

    if telematics.empty or not failures:
        return pd.DataFrame(), failures

    telematics["week_start_date"] = pd.to_datetime(
        telematics["week_start_date"]
    )

    failure_dates_by_vin = {}

    for failure in failures:
        failure_dates_by_vin.setdefault(
            failure.vin,
            [],
        ).append(pd.Timestamp(failure.failure_date))

    def next_failure_date(row):
        future_dates = [
            failure_date
            for failure_date in failure_dates_by_vin.get(row.vin, [])
            if failure_date >= row.week_start_date
        ]

        return min(future_dates) if future_dates else pd.NaT

    telematics["failure_date"] = telematics.apply(
        next_failure_date,
        axis=1,
    )

    telematics["has_future_failure"] = (
        telematics["failure_date"].notna()
    )

    # Do not treat observations after the last known failure
    # as healthy observations.
    telematics = telematics[telematics["has_future_failure"]].copy()

    telematics["days_to_fail"] = (
        telematics["failure_date"]
        - telematics["week_start_date"]
    ).dt.days

    # Positive = failure expected within 28 days.
    telematics["label"] = (
        telematics["days_to_fail"]
        .between(0, FAILURE_WINDOW_DAYS)
        .astype(int)
    )

    # Make sure the selected model features are numeric.
    for feature in FEATURES:
        if feature in telematics.columns:
            telematics[feature] = pd.to_numeric(
                telematics[feature],
                errors="coerce",
            )

    telematics = telematics.dropna(
        subset=list(FEATURES)
    ).copy()

    return telematics, failures


def _fit_model(
    training: pd.DataFrame,
    selected_signals: list[str],
):

    if training.empty:
        return None

    if training["label"].nunique() < 2:
        return None

    # Scaling makes the different telemetry signals comparable
    # and gives LogisticRegression more stable coefficients.
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=2000,
            random_state=42,
            C=1.0,
        ),
    )

    model.fit(
        training[selected_signals],
        training["label"],
    )

    return model


def _percentage(value: float) -> float:
    return round(value * 100, 2)


def calculate_backtest(
    part_code: str,
    selected_signals: list[str],
    db: Session,
) -> dict:

    normalized_part = part_code.strip().upper()

    normalized_signals = list(
        dict.fromkeys(
            signal.strip()
            for signal in selected_signals
        )
    )

    # ---------------------------------------------------------
    # Validate signals
    # ---------------------------------------------------------

    invalid_signals = [
        signal
        for signal in normalized_signals
        if signal not in FEATURES
    ]

    if invalid_signals:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "invalid_input",
            "reason": (
                f"Unknown signals: "
                f"{', '.join(invalid_signals)}"
            ),
        }

    if not normalized_signals:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": (
                "At least one historical signal is required "
                "to evaluate a rule."
            ),
        }

    # ---------------------------------------------------------
    # Load history
    # ---------------------------------------------------------

    history, failures = _load_labeled_history(
        normalized_part,
        db,
    )

    if history.empty or not failures:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": (
                f"No telematics and failure history is "
                f"available for {normalized_part}."
            ),
        }

    if history["label"].nunique() < 2:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": (
                f"Not enough positive and negative historical "
                f"observations for {normalized_part}."
            ),
        }

    if history["vin"].nunique() < 2:
        return {
            "days_to_alert": None,
            "rule_precision_pct": None,
            "rule_coverage_pct": None,
            "status": "insufficient_data",
            "reason": (
                f"At least two vehicles are required to "
                f"backtest {normalized_part}."
            ),
        }

    # ---------------------------------------------------------
    # Grouped cross-validation by VIN
    # ---------------------------------------------------------

    groups = history["vin"]

    fold_count = min(
        5,
        groups.nunique(),
    )

    true_positives = 0
    false_positives = 0
    false_negatives = 0

    out_of_sample_predictions = []

    for train_indices, test_indices in GroupKFold(
        n_splits=fold_count
    ).split(
        history,
        history["label"],
        groups,
    ):

        training = history.iloc[train_indices].copy()
        testing = history.iloc[test_indices].copy()

        model = _fit_model(
            training,
            normalized_signals,
        )

        if model is None:
            continue

        probabilities = model.predict_proba(
            testing[normalized_signals]
        )[:, 1]

        predicted = (
            probabilities >= ALERT_THRESHOLD
        )

        actual = testing["label"].to_numpy(
            dtype=bool
        )

        true_positives += int(
            np.sum(predicted & actual)
        )

        false_positives += int(
            np.sum(predicted & ~actual)
        )

        false_negatives += int(
            np.sum(~predicted & actual)
        )

        out_of_sample_predictions.append(
            testing[
                [
                    "vin",
                    "week_start_date",
                    "failure_date",
                ]
            ].assign(
                predicted=predicted,
                probability=probabilities,
            )
        )

    # ---------------------------------------------------------
    # Observation-level precision
    # ---------------------------------------------------------

    precision_denominator = (
        true_positives
        + false_positives
    )

    precision = (
        true_positives / precision_denominator
        if precision_denominator
        else 0.0
    )

    oof_predictions = (
        pd.concat(
            out_of_sample_predictions,
            ignore_index=True,
        )
        if out_of_sample_predictions
        else pd.DataFrame()
    )

    # ---------------------------------------------------------
    # Failure-level coverage
    # ---------------------------------------------------------

    detected_failures = 0
    missed_failures = 0
    evaluated_failures = 0

    failure_lead_times = []

    if not oof_predictions.empty:

        for failure in failures:

            failure_date = pd.Timestamp(
                failure.failure_date
            )

            failure_observations = oof_predictions[
                (oof_predictions["vin"] == failure.vin)
                & (
                    oof_predictions["week_start_date"]
                    <= failure_date
                )
                & (
                    oof_predictions["week_start_date"]
                    >= failure_date
                    - timedelta(days=FAILURE_WINDOW_DAYS)
                )
            ].sort_values("week_start_date")

            evaluated_failures += 1

            if failure_observations.empty:
                missed_failures += 1
                continue

            alerts = failure_observations[
                failure_observations["predicted"]
            ]

            if not alerts.empty:

                detected_failures += 1

                # IMPORTANT:
                # Use the earliest OUT-OF-SAMPLE alert.
                first_alert = alerts.iloc[0][
                    "week_start_date"
                ]

                lead_time = (
                    failure_date
                    - pd.Timestamp(first_alert)
                ).days

                failure_lead_times.append(
                    max(0, lead_time)
                )

            else:
                missed_failures += 1

    else:
        missed_failures = 0

    coverage_denominator = detected_failures + missed_failures

    coverage = (
        detected_failures / coverage_denominator
        if coverage_denominator
        else 0.0
    )

    # ---------------------------------------------------------
    # Final metrics
    # ---------------------------------------------------------

    days_to_alert = (
        round(
            float(np.mean(failure_lead_times)),
            2,
        )
        if failure_lead_times
        else None
    )

    status = (
        "weak_signal"
        if detected_failures == 0 or precision == 0.0
        else "ok"
    )

    reason = None
    if status == "weak_signal":
        reason = (
            "The selected signal(s) did not produce a reliable "
            "out-of-sample alert at the configured threshold."
        )

    return {
        "days_to_alert": days_to_alert,
        "rule_precision_pct": _percentage(
            precision
        ),
        "rule_coverage_pct": _percentage(
            coverage
        ),
        "status": status,
        "reason": reason,
        "evaluation": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "evaluated_failures": evaluated_failures,
            "total_failures": len(failures),
            "detected_failures": detected_failures,
            "missed_failures": missed_failures,
            "alert_lead_time_samples": len(
                failure_lead_times
            ),
            "selected_signals": normalized_signals,
            "alert_threshold": ALERT_THRESHOLD,
        },
    }
