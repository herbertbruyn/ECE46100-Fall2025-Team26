#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Run database migrations
echo "Applying database migrations..."
python manage.py migrate

# Start the server (this executes the CMD passed from the Dockerfile)
echo "Starting server..."
exec "$@"
