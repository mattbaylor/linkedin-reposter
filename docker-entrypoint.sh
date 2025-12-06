#!/bin/bash
set -e

# Check if VNC mode is requested
if [ -n "$DISPLAY" ]; then
    echo "🖥️  Starting VNC server..."
    
    # Clean up any leftover X lock files
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
    
    # Start Xvfb
    Xvfb :99 -screen 0 1920x1080x24 &
    XVFB_PID=$!
    export DISPLAY=:99
    
    # Wait for Xvfb to be ready
    echo "⏳ Waiting for Xvfb to start..."
    for i in {1..10}; do
        if xdpyinfo -display :99 >/dev/null 2>&1; then
            echo "✅ Xvfb is ready"
            break
        fi
        sleep 1
    done
    
    # Start window manager  
    fluxbox &
    sleep 2
    
    # Start VNC server (no password mode for simplicity)
    x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
    
    # Start websockify (VNC → WebSocket proxy for noVNC)
    echo "🌐 Starting websockify on port 6080..."
    websockify --web /app/static/novnc 6080 localhost:5900 > /tmp/websockify.log 2>&1 &
    
    echo "✅ VNC server started on port 5900"
    echo "✅ WebSocket server started on port 6080"
    echo "   Web VNC: ${APP_BASE_URL:-http://localhost:8080}/admin/vnc"
    echo "   No password required"
    echo "   Connect with Jump Desktop to localhost:5900"
fi

# Start the FastAPI application
echo "🚀 Starting LinkedIn Reposter API..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
