"""Physics-residual features for vAInu (Layer 1, item 2).

Derives "gold" features from pump-curve parameters in assets.csv:

- hydraulic head residual: measured dP across the pump vs the
  manufacturer curve H(r, Q) sagging up with DISCHARGE_RESTRICTION and
  down with IMPPELLER_WEAR
- flow estimate: curve inversion dP -> Q for assets without a flow meter
- efficiency proxy: hydraulic power / electrical power
- thermal lag residuals: bearing / winding temperature vs first-order
  lag model driven by load fraction (tau values from
  data/*/simulation_assumptions.md)

Curve model (affinity laws): on the rated curve,
H(Q) = H0 - a * Q^2 with a = (H0 - H_bep) / Q_bep^2; at speed ratio
r = n / n_rated, affinity scaling gives H(r, Q) = r^2 * H0 - a * Q^2.

Pure numpy/pandas (stack rule). NaN-safe: features are NaN wherever a
required channel is missing instead of silently degrading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import lfilter

KILO_PASCALS_PER_METER = 9.80665  # standard gravity, m/s2

# Approximate specific gravity by fluid keyword (assets.fluid strings).
_FLUID_SG_RULES: tuple[tuple[str, float], ...] = (
    ("seawater", 1.025),
    ("brackish", 1.025),
    ("fresh", 1.0),
    ("tower", 1.0),
    ("hot", 0.97),  # hot process water ~62 C
)
DEFAULT_SG = 1.0

# First-order thermal model parameters per profile
# (data/*/simulation_assumptions.md).
_THERMAL_PARAMS: dict[str, dict[str, float]] = {
    "SHIP_SW_COOLING": {"bearing_rise_k": 24.0, "bearing_tau_s": 1500.0,
                        "winding_rise_k": 70.0, "winding_tau_s": 2400.0},
    "SHIP_LT_FRESHWATER": {"bearing_rise_k": 22.0, "bearing_tau_s": 1500.0,
                           "winding_rise_k": 72.0, "winding_tau_s": 2400.0},
    "INDUSTRIAL_CW": {"bearing_rise_k": 24.0, "bearing_tau_s": 1500.0,
                      "winding_rise_k": 72.0, "winding_tau_s": 2400.0},
    "PROCESS_TRANSFER": {"bearing_rise_k": 26.0, "bearing_tau_s": 1100.0,
                         "winding_rise_k": 75.0, "winding_tau_s": 1500.0},
}
_DEFAULT_THERMAL = {"bearing_rise_k": 24.0, "bearing_tau_s": 1500.0,
                    "winding_rise_k": 72.0, "winding_tau_s": 2400.0}

PHYSICS_FEATURES = (
    "physics_speed_ratio",
    "physics_load_frac",
    "physics_head_meas_m",
    "physics_head_pred_m",
    "physics_head_residual_m",
    "physics_flow_est_m3h",
    "physics_eta_pct",
    "physics_bearing_residual_k",
    "physics_winding_residual_k",
)
PHYSICS_QUALITY_COLUMN = "physics_quality"


def fluid_specific_gravity(fluid: str) -> float:
    """Approximate specific gravity from the assets.fluid free text."""
    lowered = str(fluid).lower()
    for keyword, sg in _FLUID_SG_RULES:
        if keyword in lowered:
            return sg
    return DEFAULT_SG


def curve_coefficient(shutoff_head_m: float, rated_head_m: float,
                      rated_flow_m3_h: float) -> float:
    """Parabolic-curve coefficient: H(Q) = H0 - a * Q^2 through BEP."""
    if rated_flow_m3_h <= 0:
        return np.nan
    return (shutoff_head_m - rated_head_m) / rated_flow_m3_h**2


def head_at_speed(speed_ratio: float, flow_m3_h: "np.ndarray | float",
                  shutoff_head_m: float, coeff_a: float) -> "np.ndarray | float":
    """Rated-curve head scaled to speed ratio via affinity laws."""
    return speed_ratio**2 * shutoff_head_m - coeff_a * np.square(flow_m3_h)


def flow_from_head_m(speed_ratio: float, head_m: "np.ndarray | float",
                     shutoff_head_m: float, coeff_a: float,
                     clip_high: bool = True) -> "np.ndarray | float":
    """Curve inversion: dP -> estimated flow (NaN where head >= r^2*H0)."""
    coeff_a = max(coeff_a, 1e-9)
    disk = speed_ratio**2 * shutoff_head_m - head_m
    if clip_high:  # above curve / zero flow: report 0, not imaginary
        result = np.sqrt(np.clip(disk, 0.0, None) / coeff_a)
        return result
    result = np.sqrt(disk / coeff_a)
    return result


def efficiency_pct(flow_m3_h: "np.ndarray", head_m: "np.ndarray",
                   power_kw: "np.ndarray", sg: float) -> "np.ndarray":
    """Hydraulic output / electrical input, in percent.

    eta = rho g Q H / (1000 * P_kw) with Q in m3/h / 3600.
    """
    values = sg * KILO_PASCALS_PER_METER * (flow_m3_h / 3600.0) * head_m \
        / np.maximum(power_kw, 1e-6)
    return np.where(np.isnan(values), np.nan, 100.0 * values)


def _first_order_lag(targets: "np.ndarray", tau_s: float,
                     sample_interval_s: float) -> "np.ndarray":
    """Exponential lag smoothing: alpha = dt / (tau + dt), via lfilter."""
    alpha = sample_interval_s / (tau_s + sample_interval_s)
    outputs = lfilter([alpha], [1.0, -(1.0 - alpha)], targets)
    return outputs


def _speed_ratio_frame(asset_df: pd.DataFrame, params: pd.Series) -> pd.Series:
    """Speed ratio per row; 1.0 when DOL / speed not instrumented.

    VFD assets without a speed transmitter (T1 retrofit) are estimated
    from power: affinity law P ~ r^3 gives r ~= (P / P_rated)^(1/3),
    clipped to a plausible band, only for RUNNING rows.
    """
    rated_rpm = float(params.get("motor_rated_rpm") or np.nan)
    ratio = pd.Series(1.0, index=asset_df.index)
    if "motor_speed_rpm" in asset_df.columns and not np.isnan(rated_rpm):
        from_speed = asset_df["motor_speed_rpm"] / rated_rpm
        return from_speed.where(from_speed > 0.05)  # 0 rpm rows -> NaN
    if "motor_power_kw" in asset_df.columns:
        rated_kw = float(params.get("motor_rated_kw") or np.nan)
        if not np.isnan(rated_kw) and rated_kw > 0:
            power_ratio = asset_df["motor_power_kw"] / rated_kw
            running = (asset_df["operating_mode"] == "RUNNING") & (power_ratio > 0)
            ratio.loc[running] = np.clip(
                power_ratio[running] ** (1.0 / 3.0), 0.05, 1.2
            )
    return ratio


def add_physics_features(df: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    """Return `df` with physics_* feature columns appended.

    Per asset: parse nameplate parameters, compute hydraulic / flow /
    efficiency / thermal features where the required channels exist,
    and a coarse `physics_quality` tag (exact / estimated / none).
    """
    out = df.copy().sort_values(["asset_id", "timestamp_utc"]).reset_index(drop=True)
    for column in PHYSICS_FEATURES:
        out[column] = np.nan
    out[PHYSICS_QUALITY_COLUMN] = "none"

    for asset_id, asset_df in out.groupby("asset_id", sort=False):
        rows = assets.loc[assets["asset_id"] == asset_id]
        if rows.empty:
            continue
        params = rows.iloc[0]
        index = asset_df.index

        coeff_a = curve_coefficient(
            float(params["pump_shutoff_head_m"]),
            float(params["pump_rated_head_m"]),
            float(params["pump_rated_flow_m3_h"]),
        )
        sg = fluid_specific_gravity(params["fluid"])
        speed = _speed_ratio_frame(asset_df, params)
        out.loc[index, "physics_speed_ratio"] = speed.to_numpy()

        # Load fraction: motor current vs nameplate (works on every tier).
        if "motor_current_a" in asset_df.columns:
            load = asset_df["motor_current_a"] / float(params["motor_rated_current_a"])
            out.loc[index, "physics_load_frac"] = load.to_numpy()

        # Data availability (not column presence): the bundled CSVs carry
        # every column for every asset, with NaN where the instrument
        # doesn't exist on that asset.
        flow_ok = "flow_m3_h" in asset_df.columns \
            and asset_df["flow_m3_h"].notna().any()
        speed_ok = "motor_speed_rpm" in asset_df.columns \
            and asset_df["motor_speed_rpm"].notna().any()
        suction_ok = "suction_pressure_kpa" in asset_df.columns \
            and asset_df["suction_pressure_kpa"].notna().any()
        discharge_ok = "discharge_pressure_kpa" in asset_df.columns \
            and asset_df["discharge_pressure_kpa"].notna().any()
        has_head = suction_ok and discharge_ok

        head_meas = pd.Series(np.nan, index=index)
        if has_head and not np.isnan(coeff_a):
            head_meas = (asset_df["discharge_pressure_kpa"]
                         - asset_df["suction_pressure_kpa"]) \
                    * sg / KILO_PASCALS_PER_METER
            out.loc[index, "physics_head_meas_m"] = head_meas.to_numpy()
            if flow_ok:
                head_pred = head_at_speed(
                    speed.to_numpy(),
                    asset_df["flow_m3_h"].to_numpy(),
                    float(params["pump_shutoff_head_m"]), coeff_a,
                )
                out.loc[index, "physics_head_pred_m"] = np.asarray(head_pred, dtype=float)
                out.loc[index, "physics_head_residual_m"] = \
                    (head_meas - out.loc[index, "physics_head_pred_m"]).to_numpy()
            if flow_ok and speed_ok:
                out.loc[index, PHYSICS_QUALITY_COLUMN] = "exact"
            else:
                out.loc[index, PHYSICS_QUALITY_COLUMN] = "estimated"
            # Estimated flow for assets without a flow meter (inversion).
            if not flow_ok:
                flow_est = flow_from_head_m(
                    speed.to_numpy(), head_meas.to_numpy(),
                    float(params["pump_shutoff_head_m"]), coeff_a,
                )
                out.loc[index, "physics_flow_est_m3h"] = np.asarray(flow_est, dtype=float)

        # Efficiency proxy: needs flow, head, power; masked where idle
        # (P_kw < 1 or Q < 1) because eta is meaningless at zero load.
        if has_head and flow_ok and "motor_power_kw" in asset_df.columns \
                and asset_df["motor_power_kw"].notna().any():
            eta = efficiency_pct(
                asset_df["flow_m3_h"].to_numpy(), head_meas.to_numpy(),
                asset_df["motor_power_kw"].to_numpy(), sg,
            )
            significant = (asset_df["flow_m3_h"] > 1.0) \
                & (asset_df["motor_power_kw"] > 1.0)
            out.loc[index, "physics_eta_pct"] = np.where(
                significant.to_numpy(), eta, np.nan,
            )

        # Thermal lag residuals (bearing / winding vs load-driven model).
        thermal = _THERMAL_PARAMS.get(params.get("profile", ""), _DEFAULT_THERMAL)
        interval = float(params.get("sample_interval_s") or 10.0)
        base = asset_df["ambient_temp_c"] if "ambient_temp_c" in asset_df.columns \
            else pd.Series(np.nan, index=index)
        if "motor_current_a" in asset_df.columns:
            load = asset_df["motor_current_a"] / float(params["motor_rated_current_a"])
            for tag, rise_key, tau_key in (("bearing", "bearing_rise_k", "bearing_tau_s"),
                                           ("winding", "winding_rise_k", "winding_tau_s")):
                channel = f"{tag}_temp_c"
                rise = thermal.get(rise_key, 24.0)
                lagged = _first_order_lag(
                    (base + rise * load).fillna(0.0).to_numpy(),
                    thermal.get(tau_key, 1500.0), interval,
                )
                predicted = pd.Series(lagged, index=index).replace(0.0, np.nan)
                if channel in asset_df.columns:
                    residual = asset_df[channel] - predicted
                    out.loc[index, f"physics_{tag}_residual_k"] = residual.to_numpy()

    return out
