#!/bin/bash

# Function to run localtunnel and monitor for errors
run_localtunnel() {
    while true; do
        echo "[$(date)] Starting localtunnel..."
        
        # Run lt command and capture both stdout and stderr
        # Use stdbuf to disable buffering for real-time output
        stdbuf -oL -eL lt --port 8000 --subdomain ftt-backend-api 2>&1 | while IFS= read -r line; do
            echo "$line"
            
            # Check for error patterns in the output
            if echo "$line" | grep -E "(Error:|throw err|UnhandledPromiseRejection|ECONNREFUSED|connection refused|got socket error|tunnel server offline|connection refused|check your firewall settings)" > /dev/null; then
                echo "[$(date)] Error detected: $line"
                # Get the PID of the lt process
                pkill -f "lt --port 8000 --subdomain ftt-backend-api"
                break
            fi
        done
        
        # Wait a bit before restarting to avoid rapid restarts
        echo "[$(date)] Restarting in 2 seconds..."
        sleep 2
    done
}

# Trap to handle script termination
trap 'echo "[$(date)] Script terminated. Killing localtunnel process..."; pkill -f "lt --port 8000 --subdomain ftt-backend-api"; exit' INT TERM

# Start the monitoring loop
run_localtunnel