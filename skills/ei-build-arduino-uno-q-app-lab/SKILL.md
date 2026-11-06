---
name: ei-build-arduino-uno-q-app-lab
description: Adapt applications for Arduino UNO Q and Arduino App Lab as apps or reusable bricks, integrate Edge Impulse EIM models, connect the Linux MPU and STM32 MCU through RouterBridge, and build Flask web UIs. Use for UNO Q development, App Lab manifests and CLI workflows, model deployment, camera apps, or porting existing projects into App Lab.
metadata:
  version: "1.1.0"
---

You are an AI assistant helping develop for an Arduino UNO Q board.
You are running on my host machine, but the target environment is connected via Android Debug Bridge (ADB) or SSH.

## Critical rules

1. DO NOT run standard bash commands (like `ls`, `mkdir`, `python`) directly on the host.
2. Prefer ADB when available. To run commands on the board via ADB, wrap them in `adb shell` (e.g., `adb shell "arduino-app-cli --help"`).
3. If ADB is not available, use SSH instead (e.g., `ssh uno-q "arduino-app-cli --help"`).
4. To read files from the board, use `adb shell "cat /path/to/file"` or `ssh uno-q "cat /path/to/file"`.
5. To write files to the board, write them to this local directory first, then use `adb push <local_file> <board_path>` or `scp <local_file> uno-q:<board_path>`.
6. To inspect logs or fetch files, use `adb pull <board_path> <local_file>` or `scp uno-q:<board_path> <local_file>`.

## Guide

Use the detailed [reference](references/REFERENCE.md) selectively. Check current Arduino and Edge Impulse documentation before relying on manifest fields, brick names, filesystem paths, or CLI flags because App Lab evolves quickly.

### Route the task

- For hardware, execution modes, paths, or setup, read **Arduino UNO Q Hardware** and **Arduino App Lab Overview**.
- For a new or modified app, read **App Structure & Configuration** and **App Lab CLI Reference**.
- For reusable bricks, read **Bricks System**.
- For MCU/MPU communication, read **Bridge: MCU-MPU Communication**. Use the separate `ei-build-arduino-router-rpc` skill for raw MessagePack clients.
- For the LED matrix, read **LED Matrix Control** and **Complete Example: Python to LED Matrix via Bridge**.
- For Edge Impulse, read **Deploying Edge Impulse ML Models**. Prefer an EIM model on the Linux MPU.
- For Flask or camera work, read **Building Flask Web Apps**, **Camera & Video Handling**, and the reference example.
- For porting an existing project, read **Converting Existing Projects to App Lab Apps** before changing its layout.
- For failures, read **Storage & Dependency Management** and **Community Troubleshooting Additions**.

## Workflow

1. Inspect the existing project before generating or moving files.
2. Identify whether the target is an app, brick, MCU sketch, Linux service, or combination.
3. Confirm mutable details against the live canonical docs linked in the reference.
4. Keep real-time I/O on the STM32 MCU and networking, files, web UI, and ML on the Linux MPU unless constraints require another split.
5. Reuse the project's established manifest fields and structure; do not invent fields.
6. Pin Python dependencies and prefer Debian packages for native libraries when practical.
7. Do not commit EIM model binaries unless the user explicitly wants them versioned.
8. Validate the manifest, run the app, inspect logs, and exercise the complete MCU-to-MPU or model-to-UI path.

## Guardrails

- Use Linux APIs on the MPU and Arduino APIs in the MCU sketch.
- Use model constants and metadata rather than hardcoded input dimensions or labels.
- Treat file paths and ports in the reference as defaults to verify, not universal facts.
- Preserve user code and unrelated changes when adapting an existing app.
