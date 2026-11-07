"""Entry point for the vAInu pump-sensor analysis pipeline."""
from src.data_input import load_telemetry, split_channels
from src.math import basic_stats


def main() -> None:
    """Load telemetry and print baseline stats per channel."""
    df = load_telemetry()
    for name, frame in split_channels(df).items():
        print(f"--- {name} ---")
        print(basic_stats(frame))


if __name__ == "__main__":
    main()