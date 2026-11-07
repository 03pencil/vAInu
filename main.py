"""Entry point for the vAInu pump-sensor analysis pipeline."""
from src.data_input import (
    asset_channels,
    flag_counts,
    load_assets,
    load_telemetry,
    split_channels,
)
from src.math import basic_stats


def main() -> None:
    """Load telemetry and print baseline stats per channel."""
    df = load_telemetry()
    assets = load_assets()
    flags = flag_counts(df)

    print(f"Telemetry: {len(df):,} rows x {len(df.columns)} cols "
          f"({df['asset_id'].nunique()} assets)")
    spans = df.groupby("asset_id")["timestamp_utc"].agg(["min", "max"])
    print(spans.to_string())
    print(f"\nFlagged rows: {int((flags > 0).sum()):,} / {len(df):,}")

    for name, frame in split_channels(df).items():
        print(f"\n--- {name} ---")
        print(basic_stats(frame))

    print("\n--- instrumentation tiers ---")
    tiers = assets.sort_values("asset_id")[["asset_id", "split",
                                            "instrumentation_tier", "profile"]]
    for _, row in tiers.iterrows():
        n_ch = len(asset_channels(row["asset_id"], assets))
        print(f"{row['asset_id']}  {row['split']:<10} {row['instrumentation_tier']:<10} "
              f"{row['profile']:<20} {n_ch} channels")


if __name__ == "__main__":
    main()
