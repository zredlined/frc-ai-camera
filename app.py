#!/usr/bin/env python3
import atexit
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

WIDTH, HEIGHT, FPS = 1280, 720, 50
PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_FPS = 640, 360, 25
JPEG_QUALITY = 65
MAX_CLIPS = 5


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class CameraRecorder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._picam = None
        self._encoder = None
        self._recording = False
        self._current_file = None
        self._h264_path = None
        self._last_preview_jpeg = None
        self._next_preview_encode_at = 0.0
        self._frame_count = 0
        self._last_frame_at = None
        self._measured_fps = 0.0
        self._last_error = ""
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def _open_camera(self):
        from picamera2 import Picamera2

        cam = Picamera2()
        config = cam.create_video_configuration(
            main={"size": (WIDTH, HEIGHT), "format": "RGB888"},
            controls={"FrameRate": float(FPS)},
        )
        cam.configure(config)
        cam.start()
        time.sleep(0.5)
        log(f"[camera] started {WIDTH}x{HEIGHT} @ {FPS}fps")
        return cam

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self.stop_recording()
        with self._lock:
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        with self._lock:
            if self._picam is not None:
                try:
                    self._picam.stop()
                    self._picam.close()
                except Exception:
                    pass
                self._picam = None

    def _capture_loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    break
                cam = self._picam

            if cam is None:
                try:
                    cam = self._open_camera()
                    with self._lock:
                        self._picam = cam
                        self._last_error = ""
                except Exception as exc:
                    with self._lock:
                        self._last_error = str(exc)
                    time.sleep(2.0)
                    continue

            try:
                frame = cam.capture_array()
            except Exception as exc:
                with self._lock:
                    self._last_error = f"Frame capture failed: {exc}"
                    self._last_frame_at = None
                    self._measured_fps = 0.0
                    if self._picam is not None:
                        try:
                            self._picam.stop()
                            self._picam.close()
                        except Exception:
                            pass
                    self._picam = None
                time.sleep(1.0)
                continue

            now = time.monotonic()
            encode_preview = False
            with self._lock:
                if self._last_frame_at is not None:
                    delta = now - self._last_frame_at
                    if delta > 0:
                        inst = 1.0 / delta
                        self._measured_fps = (0.9 * self._measured_fps + 0.1 * inst) if self._measured_fps > 0 else inst
                self._last_frame_at = now
                self._frame_count += 1
                measured_fps = self._measured_fps
                recording = self._recording
                if now >= self._next_preview_encode_at:
                    self._next_preview_encode_at = now + (1.0 / PREVIEW_FPS)
                    encode_preview = True

            if encode_preview:
                jpeg = self._build_preview(frame, recording, measured_fps)
                if jpeg is not None:
                    with self._lock:
                        self._last_preview_jpeg = jpeg

    def _build_preview(self, frame, recording: bool, fps: float) -> bytes | None:
        if frame.shape[1] != PREVIEW_WIDTH or frame.shape[0] != PREVIEW_HEIGHT:
            preview = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT), interpolation=cv2.INTER_AREA)
        else:
            preview = frame.copy()

        if recording:
            cv2.putText(preview, "REC", (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

        fps_text = f"{fps:.0f} FPS" if fps > 0 else "-- FPS"
        sz, _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.putText(preview, fps_text, (preview.shape[1] - sz[0] - 14, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

        ok, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return buf.tobytes() if ok else None

    # -- Recording (hardware H.264 → remux to MP4) --

    def start_recording(self, label: str) -> Path:
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import FileOutput

        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label).strip("_") or "clip"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{ts}_{safe}.mp4"

        with self._lock:
            if self._recording:
                return self._current_file
            cam = self._picam
        if cam is None:
            raise RuntimeError("Camera not connected")

        h264_path = filepath.with_suffix(".h264")
        encoder = H264Encoder(bitrate=8_000_000)
        encoder.output = FileOutput(str(h264_path))
        cam.start_encoder(encoder)
        log(f"[rec] started → {h264_path}")

        with self._lock:
            self._encoder = encoder
            self._recording = True
            self._current_file = filepath
            self._h264_path = h264_path
        return filepath

    def stop_recording(self) -> Path | None:
        with self._lock:
            out = self._current_file
            h264_path = self._h264_path
            encoder = self._encoder
            was_recording = self._recording
            self._encoder = None
            self._recording = False
            self._current_file = None
            self._h264_path = None

        if not was_recording or encoder is None:
            return out

        try:
            encoder.stop()
        except Exception as exc:
            log(f"[rec] encoder stop error: {exc}")

        if h264_path and Path(h264_path).exists() and out:
            log(f"[rec] remuxing → {out.name}")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-framerate", str(FPS),
                     "-i", str(h264_path), "-c", "copy", str(out)],
                    capture_output=True, timeout=30,
                )
                Path(h264_path).unlink(missing_ok=True)
                log(f"[rec] done ({out.stat().st_size} bytes)")
            except Exception as exc:
                log(f"[rec] remux error: {exc}")

        self._cleanup_old_clips()
        return out

    def _cleanup_old_clips(self) -> None:
        clips = sorted(self.output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in clips[MAX_CLIPS:]:
            try:
                old.unlink()
                log(f"[cleanup] deleted {old.name}")
            except Exception:
                pass

    # -- Public helpers --

    def get_jpeg(self) -> bytes | None:
        with self._lock:
            return self._last_preview_jpeg

    def status(self) -> dict:
        with self._lock:
            return {
                "recording": self._recording,
                "measured_fps": round(self._measured_fps, 1),
                "camera_connected": self._picam is not None,
                "last_error": self._last_error,
            }

    def list_clips(self) -> list[dict]:
        files = sorted(self.output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        clips = []
        for path in files[:MAX_CLIPS]:
            stat = path.stat()
            clips.append({
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_ts": int(stat.st_mtime),
            })
        return clips


def create_app(recorder: CameraRecorder) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    logo_dir = Path(app.root_path) / "static"
    logo_filename = "team-logo.png"

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/stream.mjpg")
    def stream():
        def generate():
            while True:
                frame = recorder.get_jpeg()
                if frame is None:
                    time.sleep(0.03)
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/status")
    def api_status():
        return jsonify(recorder.status())

    @app.get("/api/clips")
    def api_clips():
        clips = recorder.list_clips()
        for c in clips:
            c["download_url"] = url_for("download_clip", filename=c["name"])
        return jsonify({"clips": clips})

    @app.get("/download/<path:filename>")
    def download_clip(filename: str):
        safe_name = secure_filename(filename)
        if not safe_name.endswith(".mp4"):
            abort(404)
        clip_path = (recorder.output_dir / safe_name).resolve()
        if clip_path.parent != recorder.output_dir.resolve() or not clip_path.exists():
            abort(404)
        return send_from_directory(recorder.output_dir.resolve(), safe_name, as_attachment=True)

    @app.post("/api/start")
    def api_start():
        payload = request.get_json(silent=True) or {}
        label = payload.get("label", "clip")
        try:
            path = recorder.start_recording(label=label)
            return jsonify({"ok": True, "file": str(path)})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/stop")
    def api_stop():
        path = recorder.stop_recording()
        return jsonify({"ok": True, "file": str(path) if path else None})

    @app.post("/api/logo")
    def api_logo():
        file = request.files.get("logo")
        if not file or not file.filename:
            return jsonify({"ok": False, "error": "No file uploaded"}), 400
        ext = Path(file.filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            return jsonify({"ok": False, "error": "Use png/jpg/jpeg/webp"}), 400
        file.save(logo_dir / logo_filename)
        return jsonify({"ok": True, "logo_url": url_for("static", filename=logo_filename)})

    return app


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="FRC Pi Camera")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--output-dir", default="recordings")
    args = parser.parse_args()

    recorder = CameraRecorder(output_dir=Path(args.output_dir))
    recorder.start()

    def shutdown(*_):
        recorder.stop()
        raise SystemExit(0)

    atexit.register(shutdown)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    app = create_app(recorder)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
