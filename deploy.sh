#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${1:-pi3.local}"
PI_USER="admin"
PI_DIR="/home/$PI_USER/frc-ai-camera"
SERVICE="frc-pi-camera.service"

FILES=(
  app.py
  requirements.txt
  templates/index.html
  static/app.js
  static/style.css
  static/team-logo-placeholder.svg
)

echo "Deploying to $PI_USER@$PI_HOST:$PI_DIR ..."

for f in "${FILES[@]}"; do
  scp -o StrictHostKeyChecking=no "$f" "$PI_USER@$PI_HOST:$PI_DIR/$f"
done

echo "Restarting $SERVICE ..."
ssh -o StrictHostKeyChecking=no "$PI_USER@$PI_HOST" "sudo systemctl restart $SERVICE"

echo "Waiting for service to start ..."
sleep 4

ssh -o StrictHostKeyChecking=no "$PI_USER@$PI_HOST" \
  "curl -s http://localhost:5000/api/status | python3 -c \"
import sys, json
d = json.load(sys.stdin)
cam = 'connected' if d['camera_connected'] else 'DISCONNECTED'
fps = d['measured_fps']
err = d['last_error']
print(f'  Camera: {cam}  FPS: {fps}')
if err: print(f'  Error: {err}')
\""

echo "Done."
