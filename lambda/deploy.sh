#!/bin/bash
# Deploy Lambda function for async artifact ingestion

set -e

FUNCTION_NAME="artifact-ingest-processor"
REGION="us-east-2"
RUNTIME="python3.11"
HANDLER="lambda_function.lambda_handler"
MEMORY=2048  # 2GB RAM
TIMEOUT=900  # 15 minutes
ROLE_ARN="arn:aws:iam::748442897107:role/service-role/artifact-ingest-processor-role-8kmv56e1"  # Set this in environment

# Create deployment package
echo "Creating deployment package..."
rm -rf package lambda.zip
mkdir -p package

# Install dependencies
pip install -r requirements.txt -t package/

# Copy Lambda function code
cp lambda_function.py package/

# Copy S3 ingest utilities from backend
cp ../backend/web/registry/api/services/s3_direct_ingest.py package/

# Copy entire src directory (Models, Services, lib, Helpers)
echo "Copying backend/src for metrics computation..."
cp -r ../backend/src/* package/

# Create zip
cd package
zip -r ../lambda.zip .
cd ..

echo "Deployment package created: lambda.zip"

# Deploy or update Lambda function
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION 2>/dev/null; then
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://lambda.zip \
        --region $REGION

    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --memory-size $MEMORY \
        --timeout $TIMEOUT \
        --region $REGION
else
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role $ROLE_ARN \
        --handler $HANDLER \
        --zip-file fileb://lambda.zip \
        --memory-size $MEMORY \
        --timeout $TIMEOUT \
        --region $REGION \
        --environment Variables="{
            DB_HOST=$DB_HOST,
            DB_NAME=$DB_NAME,
            DB_USER=$DB_USER,
            DB_PASSWORD=$DB_PASSWORD,
            AWS_STORAGE_BUCKET_NAME=$AWS_STORAGE_BUCKET_NAME
        }"
fi

echo "Lambda function deployed successfully!"
echo ""
echo "Next steps:"
echo "1. Set environment variable on EC2: USE_LAMBDA_ASYNC=true"
echo "2. Set environment variable on EC2: INGEST_LAMBDA_FUNCTION=$FUNCTION_NAME"
echo "3. Ensure EC2 IAM role has lambda:InvokeFunction permission"
echo "4. Ensure Lambda IAM role has:"
echo "   - S3 read/write access to your bucket"
echo "   - RDS connectivity (VPC access if needed)"
echo "   - CloudWatch Logs write access"
