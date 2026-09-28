from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


ANOMALY_FEATURE_COLUMNS: tuple[str, ...] = (
    "events",
    "unique_users",
    "unique_hosts",
    "nodes",
    "unique_edges",
    "repeated_events",
    "mean_events_per_edge",
    "max_events_per_edge",
    "graph_density",
    "new_edges",
    "disappeared_edges",
    "persistent_edges",
    "edge_churn",
    "new_users",
    "new_hosts",
    "user_churn",
    "host_churn",
)

FLOW_ANOMALY_FEATURE_COLUMNS: tuple[str, ...] = (
    "events",
    "unique_hosts",
    "unique_services",
    "nodes",
    "unique_host_edges",
    "unique_service_edges",
    "unique_flow_edges",
    "repeated_events",
    "mean_events_per_flow_edge",
    "max_events_per_flow_edge",
    "host_graph_density",
    "host_service_density",
    "new_flow_edges",
    "disappeared_flow_edges",
    "persistent_flow_edges",
    "flow_edge_churn",
    "new_hosts",
    "new_services",
    "host_churn",
    "service_churn",
)


def validate_anomaly_features(stats: pd.DataFrame) -> None:
    missing = [column for column in ANOMALY_FEATURE_COLUMNS if column not in stats.columns]
    if missing:
        raise ValueError(
            "Window stats are missing required anomaly feature column(s): "
            + ", ".join(missing)
        )


def score_window_anomalies(
    stats: pd.DataFrame,
    n_estimators: int = 200,
    contamination: float = 0.05,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run unsupervised structural anomaly scoring over window-level features."""

    validate_anomaly_features(stats)
    if stats.empty:
        output = stats.copy()
        output["anomaly_label"] = pd.Series(dtype="string")
        output["anomaly_score"] = pd.Series(dtype="float64")
        output["anomaly_rank"] = pd.Series(dtype="int64")
        return output

    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be in the interval (0, 0.5].")

    output = stats.copy()
    features = (
        output.loc[:, ANOMALY_FEATURE_COLUMNS]
        .apply(pd.to_numeric, errors="coerce")
        .replace([float("inf"), float("-inf")], pd.NA)
        .fillna(0.0)
    )

    if len(output) < 2:
        output["anomaly_label"] = "normal"
        output["anomaly_score"] = 0.0
        output["anomaly_rank"] = 1
        return output

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(scaled)
    predictions = model.predict(scaled)

    # IsolationForest assigns larger score_samples values to more normal points.
    output["anomaly_score"] = -model.score_samples(scaled)
    output["anomaly_label"] = [
        "anomaly" if prediction == -1 else "normal" for prediction in predictions
    ]
    output["anomaly_rank"] = (
        output["anomaly_score"].rank(method="first", ascending=False).astype(int)
    )
    return output


def score_flow_window_anomalies(
    stats: pd.DataFrame,
    n_estimators: int = 200,
    contamination: float = 0.05,
    random_state: int = 42,
) -> pd.DataFrame:
    return _score_anomalies(
        stats=stats,
        feature_columns=FLOW_ANOMALY_FEATURE_COLUMNS,
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
    )


def _score_anomalies(
    stats: pd.DataFrame,
    feature_columns: tuple[str, ...],
    n_estimators: int,
    contamination: float,
    random_state: int,
) -> pd.DataFrame:
    missing = [column for column in feature_columns if column not in stats.columns]
    if missing:
        raise ValueError(
            "Window stats are missing required anomaly feature column(s): "
            + ", ".join(missing)
        )
    if stats.empty:
        output = stats.copy()
        output["anomaly_label"] = pd.Series(dtype="string")
        output["anomaly_score"] = pd.Series(dtype="float64")
        output["anomaly_rank"] = pd.Series(dtype="int64")
        return output

    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be in the interval (0, 0.5].")

    output = stats.copy()
    features = (
        output.loc[:, feature_columns]
        .apply(pd.to_numeric, errors="coerce")
        .replace([float("inf"), float("-inf")], pd.NA)
        .fillna(0.0)
    )

    if len(output) < 2:
        output["anomaly_label"] = "normal"
        output["anomaly_score"] = 0.0
        output["anomaly_rank"] = 1
        return output

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(scaled)
    predictions = model.predict(scaled)
    output["anomaly_score"] = -model.score_samples(scaled)
    output["anomaly_label"] = [
        "anomaly" if prediction == -1 else "normal" for prediction in predictions
    ]
    output["anomaly_rank"] = (
        output["anomaly_score"].rank(method="first", ascending=False).astype(int)
    )
    return output
