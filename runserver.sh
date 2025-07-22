#!/bin/bash

# Configuration
SUBDOMAIN="ftt-backend-api"
PORT=3000  # Change this to your desired port
TUNNEL_URL="https://${SUBDOMAIN}.loca.lt"
PING_INTERVAL=10
STARTUP_TIMEOUT=10
LOG_FILE="/tmp/lt-manager.log"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${2:-}$(date '+%Y-%m-%d %H:%M:%S') - $1${NC}" | tee -a "$LOG_FILE"
}

# Function to check if tunnel is accessible
check_tunnel() {
    response=$(curl -s -o /dev/null -w "%{http_code}" -H "bypass-tunnel-reminder: true" "$TUNNEL_URL" --connect-timeout 5)
    if [ "$response" -eq 200 ] || [ "$response" -eq 301 ] || [ "$response" -eq 302 ]; then
        return 0
    else
        return 1
    fi
}

# Function to kill existing lt process
kill_lt() {
    log "Killing existing lt processes..." "$YELLOW"
    pkill -f "lt.*--subdomain.*$SUBDOMAIN" 2>/dev/null
    sleep 2
}

# Function to start localtunnel
start_tunnel() {
    log "Starting localtunnel with subdomain: $SUBDOMAIN on port: $PORT" "$GREEN"
    lt --port "$PORT" --subdomain "$SUBDOMAIN" &
    LT_PID=$!
    log "LocalTunnel started with PID: $LT_PID"
}

# Function to wait for tunnel to be ready
wait_for_tunnel() {
    log "Waiting for tunnel to be accessible (max ${STARTUP_TIMEOUT}s)..." "$YELLOW"
    start_time=$(date +%s)
    
    while true; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        
        if [ $elapsed -ge $STARTUP_TIMEOUT ]; then
            log "Timeout: Tunnel not accessible after ${STARTUP_TIMEOUT}s" "$RED"
            return 1
        fi
        
        if check_tunnel; then
            log "Tunnel is accessible at: $TUNNEL_URL" "$GREEN"
            return 0
        fi
        
        sleep 1
    done
}

# Function to monitor tunnel health
monitor_tunnel() {
    log "Starting tunnel monitoring (checking every ${PING_INTERVAL}s)..." "$GREEN"
    
    while true; do
        sleep $PING_INTERVAL
        
        if ! check_tunnel; then
            log "Tunnel is not accessible! Restarting..." "$RED"
            return 1
        fi
        
        # Check if lt process is still running
        if ! kill -0 $LT_PID 2>/dev/null; then
            log "LocalTunnel process died! Restarting..." "$RED"
            return 1
        fi
        
        log "Tunnel health check passed"
    done
}

# Main loop
main() {
    log "=== LocalTunnel Manager Started ===" "$GREEN"
    log "Subdomain: $SUBDOMAIN"
    log "Port: $PORT"
    log "Tunnel URL: $TUNNEL_URL"
    log "===================================" "$GREEN"
    
    while true; do
        # Kill any existing processes
        kill_lt
        
        # Start the tunnel
        start_tunnel
        
        # Wait for tunnel to be ready
        if wait_for_tunnel; then
            # Monitor tunnel health
            monitor_tunnel
        fi
        
        # If we reach here, something went wrong, restart
        log "Restarting tunnel..." "$YELLOW"
        kill_lt
        sleep 2
    done
}

# Trap signals to ensure clean shutdown
trap 'log "Shutting down..." "$YELLOW"; kill_lt; exit 0' SIGINT SIGTERM

# Check if required commands are available
if ! command -v lt &> /dev/null; then
    log "Error: 'lt' command not found. Please install localtunnel: npm install -g localtunnel" "$RED"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    log "Error: 'curl' command not found. Please install curl." "$RED"
    exit 1
fi

# Run the main function
main