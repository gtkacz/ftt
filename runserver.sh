#!/bin/bash

# Configuration
SUBDOMAIN="your-subdomain"
PORT="3000"
LOG_FILE="lt_monitor.log"
HEALTH_CHECK_INTERVAL=10
CURL_TIMEOUT=5

# Color codes for different log levels
declare -A LOG_COLORS=(
    ["debug"]=""
    ["info"]="\033[34m"
    ["warning"]="\033[33m"
    ["error"]="\033[91m"
    ["critical"]="\033[31m"
)

# Function to log messages with timestamp and color
log_message() {
    local message="$1"
    local level="${2:-info}"
    local color="${LOG_COLORS[$level]}"
    local reset="\033[0m"
    
    local formatted_message="[$(date)] [$level] $message"
    
    # Print to terminal with color
    if [[ -n "$color" ]]; then
        echo -e "${color}${formatted_message}${reset}"
    else
        echo "$formatted_message"
    fi
    
    # Log to file without color codes
    echo "$formatted_message" >> "$LOG_FILE"
}

# Global variable for lt process PID
LT_PID=""

# Function to start the lt command
start_lt() {
    log_message "Starting localtunnel on port $PORT with subdomain $SUBDOMAIN" "info"
    
    # Start lt command in background
    lt --port "$PORT" --subdomain "$SUBDOMAIN" &
    LT_PID=$!
    
    log_message "Started localtunnel with PID: $LT_PID" "info"
    
    # Give it a moment to initialize
    sleep 2
}

# Function to check if process is running
is_process_running() {
    local pid="$1"
    if [[ -z "$pid" ]]; then
        return 1
    fi
    
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to kill lt process if running
kill_lt() {
    if [[ -n "$LT_PID" ]] && is_process_running "$LT_PID"; then
        log_message "Killing localtunnel process $LT_PID" "warning"
        kill "$LT_PID" 2>/dev/null
        sleep 1
        
        # Force kill if still running
        if is_process_running "$LT_PID"; then
            kill -9 "$LT_PID" 2>/dev/null
            log_message "Force killed localtunnel process $LT_PID" "warning"
        fi
    fi
    LT_PID=""
}

# Function to perform health check
health_check() {
    local url="https://${SUBDOMAIN}.loca.lt/api/healthcheck/"
    
    log_message "Performing health check: $url" "debug"
    
    local response_code
    response_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout "$CURL_TIMEOUT" \
        --max-time "$CURL_TIMEOUT" \
        -H "bypass-tunnel-reminder: true" \
        "$url" 2>/dev/null)
    
    if [[ "$response_code" == "200" ]]; then
        log_message "Health check passed (HTTP $response_code)" "debug"
        return 0
    else
        log_message "Health check failed (HTTP $response_code)" "error"
        return 1
    fi
}

# Cleanup function for script termination
cleanup() {
    log_message "Script terminating, cleaning up..." "info"
    kill_lt
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Main monitoring loop
main() {
    log_message "Starting LocalTunnel monitor script" "info"
    log_message "Configuration: PORT=$PORT, SUBDOMAIN=$SUBDOMAIN" "info"
    
    while true; do
        # Start lt if not running
        if ! is_process_running "$LT_PID"; then
            if [[ -n "$LT_PID" ]]; then
                log_message "LocalTunnel process $LT_PID has died" "error"
            fi
            
            kill_lt  # Clean up any orphaned processes
            start_lt
            
            # Wait a bit for the tunnel to establish
            sleep 5
        fi
        
        # Perform health check
        if ! health_check; then
            log_message "Health check failed, restarting localtunnel" "warning"
            kill_lt
            continue
        fi
        
        # Wait before next health check
        sleep "$HEALTH_CHECK_INTERVAL"
    done
}

# Start the main function
main