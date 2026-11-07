"""Tests for src.physics — runnable via `.venv/bin/python tests/test_physics.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.data_input import load_assets, load_telemetry
from src.physics import (
    PHYSICS_FEATURES,
    add_physics_features,
    curve_coefficient,
    flow_from_head_m,
    fluid_specific_gravity,
    head_at_speed,
    _first_order_lag,
)


def test_curve_roundtrip() -> None:
    # H0=50 m, rated (300 m3/h, 30 m) -> a = (50-30)/300^2.
    a = curve_coefficient(50.0, 30.0, 300.0)
    assert a == (20.0 / 300.0**2)
    assert head_at_speed(1.0, 300.0, 50.0, a) == 30.0
    assert flow_from_head_m(1.0, 30.0, 50.0, a) == 300.0
    # Affinity: at r=0.8 the affinity point (240, 19.2) sits exactly on
    # the scaled curve.
    assert abs(head_at_speed(0.8, 240.0, 50.0, a) - 19.2) < 1e-9
    no_zealotry = flow_from_head_m(1.0, np.array([50.0]), 50.0, a)  # head >= H0
    assert (no_zealotry == 0.0).all()


def test_fluid_specific_gravity() -> None:
    assert fluid_specific_gravity("Seawater (brackish, ~6 PSU)") == 1.025
    assert fluid_specific_gravity("Treated fresh water (closed loop)") == 1.0
    assert fluid_specific_gravity("Cooling-tower water") == 1.0
    assert fluid_specific_gravity("Hot process water") == 0.97


def test_first_order_lag_converges() -> None:
    targets = np.full(10_000, 60.0)
    out = _first_order_lag(targets, tau_s=1500.0, sample_interval_s=10.0)
    assert abs(out[-1] - 60.0) < 0.5  # 10k*s >> tau: fully converged
    steady_state = _first_order_lag(np.full(240, 30.0), 2400.0, 10.0)
    # After 1 tau (2400 s = 240 samples) it must be at ~63% of target,
    # comfortably below target: 30 * (1 - exp(-1)) ~= 19.
    assert abs(steady_state[-1] - 19.0) < 1.0


def test_physics_features_on_real_data() -> None:
    df = load_telemetry(join_assets=True)
    assets = load_assets()
    out = add_physics_features(df, assets)
    for column in PHYSICS_FEATURES:
        assert column in out.columns

    # PUMP-04 (T2 full, flow+speed+power): exact quality, residual usable.
    p4 = out[out["asset_id"] == "PUMP-04"]
    assert (p4["physics_quality"] == "exact").all()
    running = p4["operating_mode"] == "RUNNING"
    res = p4.loc[running, "physics_head_residual_m"]
    assert res.notna().mean() > 0.5
    # Healthy envelope test: benign-ish rows should be close to the curve.
    benign = running & (p4["label"] == "benign") if "label" in p4.columns else running
    if benign.sum() > 50:
        assert p4.loc[benign, "physics_head_residual_m"].abs().median() < 15.0
    eta = p4.loc[running & (p4["motor_current_a"] > 0.0), "physics_eta_pct"]
    assert eta.dropna().between(10.0, 90.0).mean() > 0.8

    # PUMP-03 (T0 legacy, no suction/flow): no head features at all.
    p3 = out[out["asset_id"] == "PUMP-03"]
    assert p3["physics_head_residual_m"].isna().all()
    assert (p3["physics_quality"] == "none").all()

    # PUMP-08 (T1 retrofit: suction/discharge but no flow): estimated flow.
    p8 = out[out["asset_id"] == "PUMP-08"]
    p8_running = p8["operating_mode"] == "RUNNING"
    assert p8.loc[p8_running, "physics_flow_est_m3h"].notna().mean() > 0.5
    est = p8.loc[p8_running, "physics_flow_est_m3h"].dropna()
    assert est.between(0.0, 1200.0).all()

    # Thermal residuals exist where bearing instruments exist.
    p6 = out[out["asset_id"] == "PUMP-06"]
    assert p6["physics_bearing_residual_k"].notna().any()
    p1 = out[out["asset_id"] == "PUMP-01"]
    assert p1["physics_winding_residual_k"].isna().all()  # no winding channel


if __name__ == "__main__":
    for fn in (test_curve_roundtrip,
               test_fluid_specific_gravity,
               test_first_order_lag_converges,
               test_physics_features_on_real_data):
        fn()
        print(f"PASS {fn.__name__}")
