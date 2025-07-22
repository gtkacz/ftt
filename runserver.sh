#!/bin/bash

# Global variables
SUBDOMAIN="ftt-backend-api"
LT_PID=""
MONITOR_PID=""
HEALTH_CHECK_PID=""
LOG_FILE="/tmp/localtunnel_monitor.log"
HEALTH_CHECK_FAILED=false

# Function to log messages with timestamp
log_message() {
    echo "[$(date)] $1" | tee -a "$LOG_FILE"
}

# Function to safely kill a process with timeout
kill_process_safe() {
    local pid=$1
    local timeout=${2:-10}
    
    if [[ -z "$pid" ]]; then
        return 0
    fi
    
    # Check if process exists
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "Process $pid not found (already dead)"
        return 0
    fi
    
    log_message "Killing process $pid..."
    
    # Try SIGTERM first
    kill "$pid" 2>/dev/null
    
    # Wait for process to die gracefully
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt $timeout ]; do
        sleep 1
        ((count++))
    done
    
    # If still alive, use SIGKILL
    if kill -0 "$pid" 2>/dev/null; then
        log_message "Process $pid didn't respond to SIGTERM, using SIGKILL"
        kill -9 "$pid" 2>/dev/null
        sleep 2
        
        # Final check
        if kill -0 "$pid" 2>/dev/null; then
            log_message "WARNING: Process $pid could not be killed"
            return 1
        fi
    fi
    
    log_message "Process $pid killed successfully"
    return 0
}

# Function to check if localtunnel process is running
is_lt_running() {
    if [[ -n "$LT_PID" ]] && kill -0 "$LT_PID" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to perform health check
health_check_loop() {
    local url="https://${SUBDOMAIN}.loca.lt/api/healthcheck/"
    
    while true; do
        sleep 10
        
        if curl -s --connect-timeout 5 --max-time 10 -H "bypass-tunnel-reminder: true" "$url" > /dev/null 2>&1; then
            log_message "Health check passed for $url"
        else
            log_message "Health check FAILED for $url - triggering restart"
            HEALTH_CHECK_FAILED=true
            break
        fi
    done
}

# Function to start health check
start_health_check() {
    if [[ -n "$HEALTH_CHECK_PID" ]] && kill -0 "$HEALTH_CHECK_PID" 2>/dev/null; then
        kill_process_safe "$HEALTH_CHECK_PID" 5
    fi
    
    HEALTH_CHECK_FAILED=false
    health_check_loop &
    HEALTH_CHECK_PID=$!
    log_message "Health check started with PID: $HEALTH_CHECK_PID"
}

# Function to monitor output for errors
monitor_output() {
    local lt_pid=$1
    local url_found=false
    local start_time=$(date +%s)
    local timeout=10
    
    while IFS= read -r line; do
        echo "$line"
        
        # Check for successful URL output
        if echo "$line" | grep -i "your url is:" > /dev/null; then
            url_found=true
            log_message "URL successfully obtained: $line"
            # Start health check once URL is confirmed
            start_health_check
        fi
        
        # Check for error patterns in the output
        if echo "$line" | grep -E "(Error:|throw err|UnhandledPromiseRejection|ECONNREFUSED|connection refused|got socket error|tunnel server offline|check your firewall settings|ENOTFOUND|socket hang up)" > /dev/null; then
            log_message "Error detected in output: $line"
            return 1
        fi
        
        # Check timeout - if no URL found within 10 seconds
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [[ "$url_found" == "false" ]] && [[ $elapsed -ge $timeout ]]; then
            log_message "URL not found after $timeout seconds. Restarting..."
            return 1
        fi
    done
    
    # If we reach here, the process ended
    if [[ "$url_found" == "false" ]]; then
        log_message "Localtunnel process ended without providing URL"
        return 1
    fi
    
    log_message "Localtunnel process output ended"
    return 1
}

# Function to start localtunnel and monitor it
start_localtunnel() {
    log_message "Starting localtunnel..."
    
    # Start localtunnel in background with output monitoring
    stdbuf -oL -eL lt --port 8000 --subdomain "$SUBDOMAIN" 2>&1 | monitor_output &
    
    # Get the PID of the lt process (not the monitor)
    # We need to find the actual lt process
    sleep 2
    LT_PID=$(pgrep -f "lt --port 8000 --subdomain $SUBDOMAIN" | head -1)
    MONITOR_PID=$!
    
    if [[ -z "$LT_PID" ]]; then
        log_message "ERROR: Could not find localtunnel process PID"
        return 1
    fi
    
    log_message "Localtunnel started with PID: $LT_PID, Monitor PID: $MONITOR_PID"
    
    # Give it a moment to check for immediate failures
    sleep 3
    
    # Check if monitor is still running (it would exit if URL check failed)
    if [[ -n "$MONITOR_PID" ]] && ! kill -0 "$MONITOR_PID" 2>/dev/null; then
        log_message "Monitor process exited early (likely no URL found or error occurred)"
        return 1
    fi
    
    return 0
}

# Function to cleanup and restart
cleanup_and_restart() {
    log_message "Cleaning up and restarting..."
    
    # Kill health check process if running
    if [[ -n "$HEALTH_CHECK_PID" ]] && kill -0 "$HEALTH_CHECK_PID" 2>/dev/null; then
        kill_process_safe "$HEALTH_CHECK_PID" 5
    fi
    
    # Kill monitor process if running
    if [[ -n "$MONITOR_PID" ]] && kill -0 "$MONITOR_PID" 2>/dev/null; then
        kill_process_safe "$MONITOR_PID" 5
    fi
    
    # Kill localtunnel process if running
    if [[ -n "$LT_PID" ]]; then
        kill_process_safe "$LT_PID" 10
    fi
    
    # Also kill any remaining lt processes as fallback
    local remaining_pids=$(pgrep -f "lt --port 8000 --subdomain $SUBDOMAIN")
    if [[ -n "$remaining_pids" ]]; then
        log_message "Killing remaining localtunnel processes: $remaining_pids"
        echo "$remaining_pids" | xargs -r kill -9 2>/dev/null
    fi
    
    # Reset PIDs and flags
    LT_PID=""
    MONITOR_PID=""
    HEALTH_CHECK_PID=""
    HEALTH_CHECK_FAILED=false
    
    # Wait before restarting
    log_message "Waiting 3 seconds before restart..."
    sleep 3
}

# Function to run the main monitoring loop
run_localtunnel() {
    while true; do
        # Start localtunnel
        if ! start_localtunnel; then
            log_message "Failed to start localtunnel, retrying in 5 seconds..."
            sleep 5
            cleanup_and_restart
            continue
        fi
        
        # Monitor the process
        while true; do
            # Check if health check failed
            if [[ "$HEALTH_CHECK_FAILED" == "true" ]]; then
                log_message "Health check failed, restarting localtunnel"
                break
            fi
            
            # Check if localtunnel process is still running
            if ! is_lt_running; then
                log_message "Localtunnel process died (PID: $LT_PID not found)"
                break
            fi
            
            # Check if monitor process is still running
            if [[ -n "$MONITOR_PID" ]] && ! kill -0 "$MONITOR_PID" 2>/dev/null; then
                log_message "Output monitor detected error or process ended"
                break
            fi
            
            # Wait before next check
            sleep 5
        done
        
        # Clean up and restart
        cleanup_and_restart
    done
}

# Function to handle script termination
cleanup_on_exit() {
    log_message "Script terminated. Cleaning up..."
    
    # Kill health check process
    if [[ -n "$HEALTH_CHECK_PID" ]] && kill -0 "$HEALTH_CHECK_PID" 2>/dev/null; then
        kill_process_safe "$HEALTH_CHECK_PID" 5
    fi
    
    # Kill monitor process
    if [[ -n "$MONITOR_PID" ]] && kill -0 "$MONITOR_PID" 2>/dev/null; then
        kill_process_safe "$MONITOR_PID" 5
    fi
    
    # Kill localtunnel process
    if [[ -n "$LT_PID" ]]; then
        kill_process_safe "$LT_PID" 10
    fi
    
    # Kill any remaining lt processes
    local remaining_pids=$(pgrep -f "lt --port 8000 --subdomain $SUBDOMAIN")
    if [[ -n "$remaining_pids" ]]; then
        log_message "Killing remaining localtunnel processes: $remaining_pids"
        echo "$remaining_pids" | xargs -r kill -9 2>/dev/null
    fi
    
    log_message "Cleanup completed. Exiting."
    exit 0
}

# Trap to handle script termination
trap cleanup_on_exit INT TERM EXIT

# Create log file
touch "$LOG_FILE"
log_message "=== Localtunnel Monitor Started ==="
log_message "Log file: $LOG_FILE"
log_message "Subdomain: $SUBDOMAIN"

# Start the monitoring loop
run_localtunnel