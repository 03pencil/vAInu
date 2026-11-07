"""Entry point for the vAInu pump-sensor analysis pipeline."""
from src.data_input import load_telemetry, split_channels
from src.math import basic_stats
from src.ui import plot_channel


def main() -> None:
    df = load_telemetry()
    channels = split_channels(df)
    for name, frame in channels.items():
        print(f"--- {name} ---")
        print(basic_stats(frame))
    # plot_channel(channels["pressure"], "pressure")


if __name__ == "__main__":
    main()