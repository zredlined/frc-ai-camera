# FRC Pi Camera Recorder

A streaming camera and clip recorder for FRC robotics data collection.
Built by FRC 4419 Team Rewind.

- Live MJPEG preview in the browser
- One-button start/stop recording from the web UI
- Hardware H.264 encoding (no FPS drop while recording)
- Timestamped MP4 clips with auto-cleanup (keeps last 5)
- One-click clip downloads for Roboflow labeling
- Team logo upload

## How it works

The app runs a single Python process on the Raspberry Pi. A background thread
captures frames from the camera in a continuous loop. Two things happen with
those frames:

```
CSI Camera
    |
    v
Picamera2 capture loop (1280x720 @ 50 FPS)
    |
    |--- downsample to 640x360 --> JPEG encode (25 FPS) --> /stream.mjpg --> browser
    |
    '--- H.264 hardware encoder (1280x720 @ 50 FPS) --> .h264 --> ffmpeg remux --> .mp4
```

**Preview stream** -- Every ~40ms the latest frame is downscaled and JPEG-encoded
with an FPS counter and REC indicator overlay. The Flask `/stream.mjpg` endpoint
sends these JPEGs as a multipart HTTP stream, which the browser renders as a
live video feed via a plain `<img>` tag.

**Recording** -- When you press Record, the Pi's hardware H.264 encoder starts
writing a raw `.h264` file directly from the camera's full-resolution stream.
This happens in hardware so it doesn't slow down the preview or eat CPU. When
you stop recording, `ffmpeg` remuxes the `.h264` into a downloadable `.mp4`.

**Web UI** -- Flask serves a single HTML page. JavaScript polls `/api/status`
every second and `/api/clips` every 10 seconds. Recording start/stop are
simple POST requests to `/api/start` and `/api/stop`.

## Hardware

| Part | What we use |
|------|-------------|
| Computer | Raspberry Pi 3 (Pi 4/5 also work) |
| Camera | Sony IMX296 global shutter (CSI interface) |
| Cable | CSI ribbon cable (15-pin, matches your Pi) |
| Storage | microSD card, 16 GB+ |
| OS | Raspberry Pi OS Bookworm (64-bit) |
| Power | Official Pi power supply |

The camera must be connected via the CSI ribbon cable (not USB). Make sure the
camera interface is enabled -- run `sudo raspi-config`, go to Interface Options,
and enable the camera if it isn't already.

## First-time Pi setup

1. Install dependencies:

```bash
sudo apt update
sudo apt install -y python3-opencv python3-flask python3-picamera2 ffmpeg
```

2. Clone this repo:

```bash
cd ~
git clone https://github.com/zredlined/frc-ai-camera.git
cd frc-ai-camera
```

3. Test that it runs:

```bash
python3 app.py
```

Open `http://<pi-ip>:5000` from your laptop. You should see the live feed.
Press `Ctrl+C` to stop.

4. Set up as a system service (starts automatically on boot):

```bash
sudo tee /etc/systemd/system/frc-pi-camera.service > /dev/null << 'EOF'
[Unit]
Description=FRC Pi Camera Recorder
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/frc-ai-camera
ExecStart=/usr/bin/python3 /home/admin/frc-ai-camera/app.py --output-dir /home/admin/frc-ai-camera/recordings
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable frc-pi-camera.service
sudo systemctl start frc-pi-camera.service
```

Change `User` and `WorkingDirectory` if your Pi username isn't `admin`.

Check that it's running:

```bash
sudo systemctl status frc-pi-camera.service
```

## Deploying code changes

From your laptop, run the deploy script:

```bash
./deploy.sh <pi-hostname-or-ip>
```

This copies the code to the Pi and restarts the service. Default host is
`pi3.local` if you don't pass one.

## Recording clips

- Set a label (e.g. `yellow_ball`) in the web UI before recording.
- Record short clips (10-45 seconds) so they're easy to label in Roboflow.
- Vary distance, lighting, and backgrounds between clips.
- Download clips directly from the Recent Clips list in the web UI.

Clips are stored in `recordings/` on the Pi. Only the last 5 are kept --
download any you want to keep before they get auto-deleted.

## Bulk copy clips

From your laptop:

```bash
scp -r admin@<pi-ip>:~/frc-ai-camera/recordings ./recordings_from_pi
```

## CLI options

```
python3 app.py --help
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `5000` | Web server port |
| `--output-dir` | `recordings` | Where MP4 clips are saved |

Camera defaults: 1280x720 @ 50 FPS capture, 640x360 @ 25 FPS preview, JPEG quality 65.

## Team branding

Click **Upload Team Logo** in the web UI. Supports `.png`, `.jpg`, `.jpeg`, `.webp`.
