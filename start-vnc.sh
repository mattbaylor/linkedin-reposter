#!/bin/bash
# Start VNC server for LinkedIn manual setup

# Set VNC password (change this!)
export VNC_PASSWORD="${VNC_PASSWORD:-linkedin123}"

# Start Xvfb (virtual framebuffer)
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait for Xvfb to start
sleep 2

# Start window manager
fluxbox &

# Start VNC server
x11vnc -display :99 -forever -shared -rfbauth /tmp/.vncpasswd -rfbport 5900 &

echo "VNC server started on port 5900"
echo "Password: $VNC_PASSWORD"
echo "Connect with: localhost:5900"

# Keep script running
wait
