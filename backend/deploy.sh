#!/bin/bash
set -e

BASE_REPO="748442897107.dkr.ecr.us-east-2.amazonaws.com"
REPO="748442897107.dkr.ecr.us-east-2.amazonaws.com/461-project/backend:latest"

# Login to ECR
aws ecr get-login-password --region us-east-2 \
  | docker login --username AWS --password-stdin $BASE_REPO

# Stop and remove old container
docker stop backend || true
docker rm backend || true

# Remove old image to free space
docker rmi $REPO || true
# Prune dangling images to keep disk clean
docker image prune -f

# Pull latest image
docker pull $REPO

# Run new container
docker run -d --name backend -p 8000:8000 -e DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY -e ALLOWED_HOSTS=$ALLOWED_HOSTS -e GEN_AI_STUDIO_API_KEY=$GEN_AI_STUDIO_API_KEY $REPO
