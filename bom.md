# Bill of Materials (BOM)

> Minimal hardware to run the pump-sensor pipeline on an Arduino UNO Q with
> SmolLM served by Ollama. Bare minimum only — no cameras, display, bricks or case.

## Hardware

| # | Item | Qty | Purpose | Notes |
|---|------|:---:|---------|-------|
| 1 | Arduino UNO Q — ABX00173 (4 GB RAM / 32 GB eMMC) | 1 | Runs Ollama + SmolLM on the MPU, receives telemetry on the MCU | **Provided** by Majos Hacking League. 2 GB variant (ABX00162) works only with the smallest quantized SmolLM |
| 2 | USB-C power supply, 5 V / 3 A | 1 | Board power | Required for sustained LLM inference; a PC USB port is not reliable enough |
| 3 | USB-C data cable (USB 2.0, USB-A → C) | 1 | Initial setup: ADB / App Lab flashing from host PC | Cheap cable is fine; can stay plugged into the host PC |
| 4 | Local Wi-Fi network (existing router/hotspot) | 1 | Serves the web UI on the local network; pulls SmolLM into Ollama | Wi-Fi is built in, no external antenna needed |
| 5 | UART jumper wires (DuPont M-F, TX/RX/GND) | 1 set (3) | Logic box → UNO Q MCU serial feed | UNO Q digital I/O is **3.3 V** logic; add a level shifter only if the logic box drives 5 V |

## Software (no cost)

- Arduino App Lab (preloaded on the board).
- Ollama on the MPU.
- SmolLM GGUF pulled from the Ollama library (~0.4–1.7 GB; fits the 16/32 GB eMMC).

## Deliberately excluded (not needed)

Monitor/keyboard, USB-C hub, camera, Modulino bricks, shields, micro-SD, enclosure,
barrel-jack PSU. The board is tethered to the host PC for setup and then runs
headless on Wi-Fi, powered by the USB-C wall adapter.
