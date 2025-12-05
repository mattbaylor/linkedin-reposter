#!/bin/bash
set -e

# Check if VNC mode is requested
if [ -n "$DISPLAY" ]; then
    echo "🖥️  Starting VNC server..."
    
    # Start Xvfb
    Xvfb :99 -screen 0 1920x1080x24 &
    export DISPLAY=:99
    
    # Wait for Xvfb
    sleep 3
    
    # Start window manager  
    fluxbox &
    sleep 1
    
    # Start VNC server (no password mode for simplicity)
    x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
    
    echo "✅ VNC server started on port 5900"
    echo "   No password required"
    echo "   Connect with Jump Desktop to localhost:5900"
fi

# Start the FastAPI application
echo "🚀 Starting LinkedIn Reposter API..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
