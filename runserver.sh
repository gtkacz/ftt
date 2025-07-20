#!/bin/bash 
while ! lt --port 8000 --subdomain ftt-backend-api; do echo "fail"; sleep 2; done

