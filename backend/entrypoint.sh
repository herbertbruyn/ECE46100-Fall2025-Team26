#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Run database migrations
echo "Applying database migrations..."
python web/registry/manage.py migrate
# setup auth
echo "Setting up authentication..."
python web/registry/manage.py setup_auth

# Start background worker
echo "Starting background worker..."
python web/registry/worker.py &

# Start the server (this executes the CMD passed from the Dockerfile)
echo "Starting server..."
exec "$@"
