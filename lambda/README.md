# Lambda-Based Async Artifact Ingestion

This directory contains the AWS Lambda function for async artifact processing, implementing the **202 Accepted** pattern from the OpenAPI spec.

## Architecture Overview

```
User → EC2 Django → Lambda → S3 + RDS
         (202)       (async)
```

## How It Works

### EC2 Django (Fast - <100ms)

Handles synchronous validation and returns immediately:

| Status Code | When                                  | Response                                    |
| ----------- | ------------------------------------- | ------------------------------------------- |
| **400**     | Invalid request body/parameters       | `{"detail": "error message"}`               |
| **403**     | Authentication failed                 | `{"detail": "auth error"}`                  |
| **409**     | Artifact already exists               | `{"detail": "...", "existing_id": 123}`     |
| **202**     | Validation passed, processing started | `{"artifact_id": 123, "status": "pending"}` |

### Lambda Function (Async - 2-15 min)

Handles heavy processing:

1. **Download** HuggingFace files directly to S3 (status: `downloading`)
2. **Create** zip archive in S3
3. **Compute** ratings (status: `rating`)
4. **Check** threshold:
   - If rating < 0.5 → status: `rejected` (424 logic - artifact dropped)
   - If rating >= 0.5 → status: `completed`
5. **Cleanup** temporary S3 files

### Client Workflow

```python
# 1. Upload artifact
response = POST /artifact/model
{
    "url": "https://huggingface.co/bert-base-uncased"
}

# Response: 202 Accepted
{
    "artifact_id": 123,
    "status": "pending",
    "message": "Processing asynchronously..."
}

# 2. Poll for completion
while True:
    response = GET /artifacts/model/123

    if response.status == "completed":
        # Download available!
        download_url = response.data.download_url
        break

    elif response.status == "rejected":
        # Rating failed threshold (424 logic)
        print("Artifact rejected")
        break

    elif response.status in ["pending", "downloading", "rating"]:
        # Still processing
        time.sleep(5)
        continue

    elif response.status == "failed":
        # Processing error
        print(f"Error: {response.status_message}")
        break
```

## Deployment

### Prerequisites

1. **AWS Account** with permissions for:

   - Lambda function creation
   - IAM role management
   - S3 access
   - RDS access (or use API callback for SQLite)

2. **RDS PostgreSQL** (recommended) or SQLite with API callback

3. **S3 Bucket** for artifact storage

### Step 1: Set Up IAM Roles

#### Lambda Execution Role

Create IAM role `lambda-artifact-ingest-role` with:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": ["arn:aws:s3:::YOUR-BUCKET/*", "arn:aws:s3:::YOUR-BUCKET"]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

If using RDS, also attach VPC permissions and add Lambda to VPC.

#### EC2 Role Update

Add Lambda invoke permission to EC2 instance role:

```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:us-east-2:*:function:artifact-ingest-processor"
}
```

### Step 2: Deploy Lambda Function

```bash
cd lambda/

# Set environment variables
export LAMBDA_ROLE_ARN="arn:aws:iam::YOUR-ACCOUNT:role/lambda-artifact-ingest-role"
export DB_HOST="your-rds-endpoint.rds.amazonaws.com"
export DB_NAME="registry"
export DB_USER="registry_user"
export DB_PASSWORD="your-password"
export AWS_STORAGE_BUCKET_NAME="your-artifact-bucket"

# Deploy
./deploy.sh
```

### Step 3: Configure EC2 Environment

Add to `~/.env` on EC2 instance:

```bash
# Enable Lambda async mode
USE_LAMBDA_ASYNC=true

# Lambda function name
INGEST_LAMBDA_FUNCTION=artifact-ingest-processor

# S3 bucket (shared with Lambda)
AWS_STORAGE_BUCKET_NAME=your-artifact-bucket

# Database credentials (if using RDS)
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_NAME=registry
DB_USER=registry_user
DB_PASSWORD=your-password
```

### Step 4: Restart Backend

```bash
# SSH to EC2
ssh ec2-user@your-ec2-instance

# Restart Docker container
docker stop backend
docker rm backend

# Run with new environment
cd /home/ec2-user/backend
./deploy.sh
```

## Testing

### Test 202 Response

```bash
# Should return 202 immediately
curl -X POST http://your-ec2:8000/artifact/model \
  -H "Content-Type: application/json" \
  -d '{"url": "https://huggingface.co/google-bert/bert-base-uncased"}'

# Response:
{
  "artifact_id": 123,
  "status": "pending",
  "message": "Artifact ingest accepted. Processing asynchronously."
}
```

### Monitor Lambda Execution

```bash
# View Lambda logs
aws logs tail /aws/lambda/artifact-ingest-processor --follow
```

### Check Artifact Status

```bash
# Poll for completion
curl http://your-ec2:8000/artifacts/model/123

# When completed:
{
  "metadata": {
    "id": 123,
    "name": "bert-base-uncased",
    "type": "model"
  },
  "data": {
    "url": "https://huggingface.co/...",
    "download_url": "https://s3.amazonaws.com/..."
  }
}
```

## Status Codes Reference

| Code    | Source | Meaning                                     | Response                  |
| ------- | ------ | ------------------------------------------- | ------------------------- |
| **400** | EC2    | Bad request (invalid URL, malformed JSON)   | Synchronous error         |
| **403** | EC2    | Authentication failed                       | Synchronous error         |
| **409** | EC2    | Artifact already exists or processing       | Synchronous error         |
| **202** | EC2    | Accepted, processing asynchronously         | Success - poll for status |
| **424** | Lambda | Rating failed threshold (artifact rejected) | Async - status="rejected" |
| **500** | Both   | Server error                                | Error details in response |

## Cost Estimate

**Lambda Costs** (1000 model ingests/month):

- Memory: 2GB
- Duration: ~3 min average
- Compute: 1000 × 3 min × 2GB = 6,000 GB-minutes
- Cost: ~$2-3/month

**S3 Costs**:

- Storage: ~$0.023/GB/month
- Requests: Minimal (~$0.01/month)

**Total**: ~$3-5/month vs $35/month for larger EC2 instance

## Troubleshooting

### Lambda timeout

Increase timeout in `deploy.sh`:

```bash
TIMEOUT=900  # 15 minutes (max)
```

### Out of memory in Lambda

Increase RAM in `deploy.sh`:

```bash
MEMORY=4096  # 4GB
```

### Database connection issues

- **RDS**: Ensure Lambda is in same VPC as RDS
- **SQLite**: Use API callback mode (not recommended for production)

### EC2 can't invoke Lambda

Check EC2 IAM role has `lambda:InvokeFunction` permission

## Switching Back to Synchronous Mode

To disable Lambda async mode:

```bash
# On EC2, edit ~/.env
USE_LAMBDA_ASYNC=false

# Restart backend
docker restart backend
```

This will use the S3-optimized sync service instead.
