# FRC Pi Camera Recorder

Raspberry Pi camera recorder for FRC data collection:

- Live MJPEG preview in browser
- Start/stop recording from the web UI
- Hardware H.264 encoding (no FPS drop while recording)
- Timestamped MP4 clips with auto-cleanup (keeps last 5)
- One-click clip downloads
- Team logo upload

## Setup on Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-opencv python3-flask python3-picamera2 ffmpeg
```

Clone this repo onto the Pi, then run:

```bash
cd frc-pi-camera
python3 app.py
```

The server starts on port 5000 by default.

## Open from your laptop

Find the Pi's IP address (on the Pi):

```bash
hostname -I
```

Then open `http://<pi-ip>:5000` in your browser.

## Recording clips for Roboflow

- Set a label (e.g. `yellow_ball`) before recording.
- Record short clips (10-45s) for easy labeling.
- Vary distance, lighting, and backgrounds.
- Download clips directly from the web UI.

Clips are stored in `recordings/` and auto-cleaned to the most recent 5.

## Bulk copy clips to your laptop

```bash
scp -r pi@<pi-ip>:~/frc-pi-camera/recordings ./recordings_from_pi
```

## CLI options

```
python3 app.py --help
```

| Flag           | Default      | Description              |
|----------------|--------------|--------------------------|
| `--host`       | `0.0.0.0`   | Bind address             |
| `--port`       | `5000`       | Web server port          |
| `--output-dir` | `recordings` | Where MP4 clips are saved |

Camera defaults: 1280x720 @ 50 FPS, 640x360 preview @ 25 FPS.

## Team branding

Click **Upload Team Logo** in the web UI. Supports `.png`, `.jpg`, `.jpeg`, `.webp`.
