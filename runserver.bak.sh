#!/bin/bash

# Global variables
SUBDOMAIN="ftt-backend-api"
LT_PID=""
MONITOR_PID=""
HEALTH_CHECK_PID=""
LOG_FILE="/tmp/localtunnel_monitor.log"
HEALTH_STATUS_FILE="/tmp/localtunnel_health_status"
HEALTH_CHECK_FAILED=false

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

# Function to safely kill a process with timeout
kill_process_safe() {
    local pid=$1
    local timeout=${2:-10}

    if [[ -z "$pid" ]]; then
        return 0
    fi

    # Check if process exists
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "Process $pid not found (already dead)" "debug"
        return 0
    fi

    log_message "Killing process $pid..." "warning"

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
        log_message "Process $pid didn't respond to SIGTERM, using SIGKILL" "warning"
        kill -9 "$pid" 2>/dev/null
        sleep 2

        # Final check
        if kill -0 "$pid" 2>/dev/null; then
            log_message "WARNING: Process $pid could not be killed" "error"
            return 1
        fi
    fi

    log_message "Process $pid killed successfully" "info"
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

# Independent health check process
health_check_process() {
    local url="https://${SUBDOMAIN}.loca.lt/api/healthcheck/"
    local consecutive_failures=0
    local max_failures=3

    log_message "Independent health check process started (PID: $$)" "info"

    # Wait for initial setup
    sleep 15

    while true; do
        if curl -s --connect-timeout 5 --max-time 10 -H "bypass-tunnel-reminder: true" "$url" > /dev/null 2>&1; then
            consecutive_failures=0
            echo "healthy" > "$HEALTH_STATUS_FILE"
            log_message "Health check passed for $url" "debug"
        else
            ((consecutive_failures++))
            log_message "Health check failed for $url (failure $consecutive_failures/$max_failures)" "warning"

            if [[ $consecutive_failures -ge $max_failures ]]; then
                log_message "Health check FAILED $max_failures times - marking for restart" "error"
                echo "failed" > "$HEALTH_STATUS_FILE"

                # Send signal to main process if it exists
                local main_pid=$(pgrep -f "bash.*$(basename "$0")" | grep -v $$)
                if [[ -n "$main_pid" ]]; then
                    log_message "Sending restart signal to main process (PID: $main_pid)" "warning"
                    kill -USR1 "$main_pid" 2>/dev/null
                fi

                # Reset failure count and wait longer before next check
                consecutive_failures=0
                sleep 30
                continue
            fi
        fi

        sleep 10
    done
}

# Function to start independent health check
start_health_check() {
    # Kill existing health check if running
    if [[ -n "$HEALTH_CHECK_PID" ]] && kill -0 "$HEALTH_CHECK_PID" 2>/dev/null; then
        kill_process_safe "$HEALTH_CHECK_PID" 5
    fi

    # Clear previous status
    echo "unknown" > "$HEALTH_STATUS_FILE"

    # Start health check as completely independent process
    health_check_process &
    HEALTH_CHECK_PID=$!
    disown $HEALTH_CHECK_PID  # Detach from parent shell

    log_message "Independent health check started with PID: $HEALTH_CHECK_PID" "info"
}

# Function to check health status from file
check_health_status() {
    if [[ -f "$HEALTH_STATUS_FILE" ]]; then
        local status=$(cat "$HEALTH_STATUS_FILE" 2>/dev/null)
        if [[ "$status" == "failed" ]]; then
            HEALTH_CHECK_FAILED=true
            # Clear the failed status
            echo "checking" > "$HEALTH_STATUS_FILE"
        fi
    fi
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
            log_message "URL successfully obtained: $line" "info"
            # Start health check once URL is confirmed
            start_health_check
        fi

        # Check for error patterns in the output
        if echo "$line" | grep -E "(Error:|throw err|UnhandledPromiseRejection|ECONNREFUSED|connection refused|got socket error|tunnel server offline|check your firewall settings|ENOTFOUND|socket hang up)" > /dev/null; then
            log_message "Error detected in output: $line" "error"
            return 1
        fi

        # Check timeout - if no URL found within 10 seconds
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        if [[ "$url_found" == "false" ]] && [[ $elapsed -ge $timeout ]]; then
            log_message "URL not found after $timeout seconds. Restarting..." "warning"
            return 1
        fi
    done

    # If we reach here, the process ended
    if [[ "$url_found" == "false" ]]; then
        log_message "Localtunnel process ended without providing URL" "error"
        return 1
    fi

    log_message "Localtunnel process output ended" "warning"
    return 1
}

# Function to start localtunnel and monitor it
start_localtunnel() {
    log_message "Starting localtunnel..." "info"

    # Start localtunnel in background with output monitoring
    stdbuf -oL -eL lt --port 8000 --subdomain "$SUBDOMAIN" 2>&1 | monitor_output &

    # Get the PID of the lt process (not the monitor)
    # We need to find the actual lt process
    sleep 2
    LT_PID=$(pgrep -f "lt --port 8000 --subdomain $SUBDOMAIN" | head -1)
    MONITOR_PID=$!

    if [[ -z "$LT_PID" ]]; then
        log_message "ERROR: Could not find localtunnel process PID" "critical"
        return 1
    fi

    log_message "Localtunnel started with PID: $LT_PID, Monitor PID: $MONITOR_PID" "info"

    # Give it a moment to check for immediate failures
    sleep 3

    # Check if monitor is still running (it would exit if URL check failed)
    if [[ -n "$MONITOR_PID" ]] && ! kill -0 "$MONITOR_PID" 2>/dev/null; then
        log_message "Monitor process exited early (likely no URL found or error occurred)" "error"
        return 1
    fi

    return 0
}

# Function to cleanup and restart
cleanup_and_restart() {
    log_message "Cleaning up and restarting..." "warning"

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
        log_message "Killing remaining localtunnel processes: $remaining_pids" "warning"
        echo "$remaining_pids" | xargs -r kill -9 2>/dev/null
    fi

    # Reset PIDs and flags
    LT_PID=""
    MONITOR_PID=""
    HEALTH_CHECK_FAILED=false

    # Wait before restarting
    log_message "Waiting 3 seconds before restart..." "info"
    sleep 3
}

# Signal handler for health check restart requests
handle_restart_signal() {
    log_message "Received restart signal from health check" "warning"
    HEALTH_CHECK_FAILED=true
}

# Function to run the main monitoring loop
run_localtunnel() {
    # Set up signal handler for health check restart requests
    trap handle_restart_signal USR1

    while true; do
        # Start localtunnel
        if ! start_localtunnel; then
            log_message "Failed to start localtunnel, retrying in 5 seconds..." "error"
            sleep 5
            cleanup_and_restart
            continue
        fi

        # Monitor the process
        while true; do
            # Check health status from independent process
            check_health_status

            # Check if health check failed
            if [[ "$HEALTH_CHECK_FAILED" == "true" ]]; then
                log_message "Health check failed, restarting localtunnel" "warning"
                break
            fi

            # Check if localtunnel process is still running
            if ! is_lt_running; then
                log_message "Localtunnel process died (PID: $LT_PID not found)" "error"
                break
            fi

            # Check if monitor process is still running
            if [[ -n "$MONITOR_PID" ]] && ! kill -0 "$MONITOR_PID" 2>/dev/null; then
                log_message "Output monitor detected error or process ended" "warning"
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
    log_message "Script terminated. Cleaning up..." "warning"

    # Kill health check process (independent process)
    if [[ -n "$HEALTH_CHECK_PID" ]] && kill -0 "$HEALTH_CHECK_PID" 2>/dev/null; then
        kill_process_safe "$HEALTH_CHECK_PID" 5
    fi

    # Also try to kill any health check processes by name
    local health_pids=$(pgrep -f "health_check_process")
    if [[ -n "$health_pids" ]]; then
        log_message "Killing independent health check processes: $health_pids" "warning"
        echo "$health_pids" | xargs -r kill 2>/dev/null
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
        log_message "Killing remaining localtunnel processes: $remaining_pids" "warning"
        echo "$remaining_pids" | xargs -r kill -9 2>/dev/null
    fi

    # Clean up status file
    rm -f "$HEALTH_STATUS_FILE"

    log_message "Cleanup completed. Exiting." "info"
    exit 0
}

# Trap to handle script termination
trap cleanup_on_exit INT TERM EXIT

# Create log file and status file
touch "$LOG_FILE"
touch "$HEALTH_STATUS_FILE"

log_message "=== Localtunnel Monitor Started ===" "info"
log_message "Log file: $LOG_FILE" "info"
log_message "Health status file: $HEALTH_STATUS_FILE" "info"
log_message "Subdomain: $SUBDOMAIN" "info"

# Start the monitoring loop
run_localtunnel
