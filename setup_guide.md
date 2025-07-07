# Setup Guide for LLM Summariser Evaluator

This guide provides step-by-step instructions to set up the LLM Summariser Evaluator project on AWS. The project allows users to upload CSV data, summarize selected columns using AI models, and evaluate the summaries. It uses AWS S3 for hosting the frontend and storing files, AWS Lambda for processing, and API Gateway for exposing the backend. This guide is designed for users with minimal AWS or coding experience, using screenshots for clarity.

## Prerequisites
- An AWS account with permissions to create S3 buckets, Lambda functions, API Gateway APIs, and IAM roles.
- The project files (`index.html`, `summarizeData.py`, `modelJudge.py`) from the GitHub repository.
- Screenshots from the repository’s `docs/screenshots/` folder to guide you through the AWS console.

## Step 1: Create an S3 Bucket
1. Go to the [S3 console](https://s3.console.aws.amazon.com/s3/home).
2. Click **Create bucket**.
3. Enter a unique bucket name, e.g., `my-model-evaluation`. Note: Replace `my-model-evaluation` with your chosen name throughout this guide.
4. Select **US East (N. Virginia)** as the region to match the provided IAM roles.
5. Keep default settings and click **Create bucket**.
6. In the bucket’s **Properties** tab, find **Static website hosting** and click **Edit**.
7. Select **Enable** and set **Index document** to `index.html`.
8. Click **Save changes**.
9. Note the website endpoint (e.g., `http://my-model-evaluation.s3-website-us-east-1.amazonaws.com`).

   ![S3 Bucket Configuration](screenshots/s3_bucket.png)

10. In the **Permissions** tab, click **Edit** under **CORS configuration**.
11. Add the following CORS policy to allow the frontend to interact with API Gateway:
    ```json
    [
        {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedOrigins": ["*"],
            "ExposeHeaders": [],
            "MaxAgeSeconds": 3000
        }
    ]
    ```
12. Click **Save changes**.

   ![S3 CORS Configuration](screenshots/s3_cors.png)

13. (Optional) If the frontend needs public access, add a bucket policy in the **Permissions** tab under **Bucket policy**:
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::my-model-evaluation/*"
            }
        ]
    }
    ```
14. Click **Save changes**.

   ![S3 Bucket Policy](screenshots/s3_policy.png)

## Step 2: Create IAM Roles
You need two IAM roles: one for the `summarizeData` Lambda function and one for the `modelJudge` Lambda function.

### For summarizeData Lambda
1. Go to the [IAM console](https://console.aws.amazon.com/iam/).
2. Click **Roles** > **Create role**.
3. Select **AWS service** and choose **Lambda** as the use case.
4. Click **Next: Permissions**.
5. Create a custom policy by clicking **Create policy**:
   - Select **JSON** and paste the following:
     ```json
     {
         "Version": "2012-10-17",
         "Statement": [
             {
                 "Sid": "S3ListAndReadWrite",
                 "Effect": "Allow",
                 "Action": [
                     "s3:ListBucket",
                     "s3:GetObject",
                     "s3:PutObject",
                     "s3:DeleteObject"
                 ],
                 "Resource": [
                     "arn:aws:s3:::my-model-evaluation",
                     "arn:aws:s3:::my-model-evaluation/*"
                 ]
             },
             {
                 "Sid": "InvokeBedrockModels",
                 "Effect": "Allow",
                 "Action": [
                     "bedrock:InvokeModel",
                     "bedrock:InvokeModelWithResponseStream"
                 ],
                 "Resource": [
                     "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
                     "arn:aws:bedrock:*::foundation-model/mistral.mistral-7b-instruct-v0:2",
                     "arn:aws:bedrock:*::foundation-model/meta.llama3-3-70b-instruct-v1:0",
                     "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0",
                     "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0",
                     "arn:aws:bedrock:us-east-1:349440382087:inference-profile/us.meta.llama3-1-8b-instruct-v1:0",
                     "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-1-8b-instruct-v1:0",
                     "arn:aws:bedrock:us-east-2::foundation-model/meta.llama3-1-8b-instruct-v1:0"
                 ]
             },
             {
                 "Sid": "AllowInvokeLlama3",
                 "Effect": "Allow",
                 "Action": [
                     "bedrock:InvokeModel",
                     "bedrock:InvokeModelWithResponseStream"
                 ],
                 "Resource": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0"
             },
             {
                 "Effect": "Allow",
                 "Action": [
                     "bedrock:InvokeModel",
                     "bedrock:GetInferenceProfile"
                 ],
                 "Resource": "*"
             },
             {
                 "Sid": "CloudWatchLogs",
                 "Effect": "Allow",
                 "Action": [
                     "logs:CreateLogGroup",
                     "logs:CreateLogStream",
                     "logs:PutLogEvents"
                 ],
                 "Resource": "*"
             }
         ]
     }
     ```
   - Name the policy, e.g., `summarizeDataPolicy`.
   - Click **Create policy**.
6. Attach the policy to the role and click **Next**.
7. Name the role, e.g., `summarizeDataRole`.
8. Click **Create role**.

### For modelJudge Lambda
1. Repeat the above steps to create another role.
2. Create a custom policy with the following JSON, adding `s3:PutObjectAcl` for potential `UPLOAD_ACL` settings:
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockModelAndEvaluation",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:GetInferenceProfile",
                    "bedrock:CreateEvaluationJob",
                    "bedrock:GetEvaluationJob",
                    "bedrock:ListEvaluationJobs"
                ],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
                    "arn:aws:bedrock:*::foundation-model/mistral.mistral-7b-instruct-v0:2",
                    "arn:aws:bedrock:*::foundation-model/meta.llama3-3-70b-instruct-v1:0",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0",
                    "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0",
                    "arn:aws:bedrock:us-east-1:349440382087:inference-profile/us.meta.llama3-1-8b-instruct-v1:0",
                    "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-1-8b-instruct-v1:0",
                    "arn:aws:bedrock:us-east-2::foundation-model/meta.llama3-1-8b-instruct-v1:0",
                    "arn:aws:bedrock:us-east-1:349440382087:inference-profile/us.deepseek.r1-v1:0",
                    "arn:aws:bedrock:us-east-1:349440382087:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
                ]
            },
            {
                "Sid": "S3Access",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:DeleteObject",
                    "s3:PutObjectAcl"
                ],
                "Resource": [
                    "arn:aws:s3:::my-model-evaluation/*",
                    "arn:aws:s3:::my-model-evaluation/temp2/*"
                ]
            },
            {
                "Sid": "KMSAccess",
                "Effect": "Allow",
                "Action": [
                    "kms:Decrypt",
                    "kms:GenerateDataKey",
                    "kms:DescribeKey"
                ],
                "Resource": [
                    "arn:aws:kms:us-east-1:349440382087:key/d4cc87ff-4d33-445c-bf2a-756a8de1e1d3"
                ]
            },
            {
                "Sid": "CloudWatchLogs",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "*"
            }
        ]
    }
    ```
3. Name the policy, e.g., `modelJudgePolicy`.
4. Attach the policy to the role and name it, e.g., `modelJudgeRole`.
5. Click **Create role**.

## Step 3: Deploy Lambda Functions
### Create summarizeData Lambda
1. Go to the [Lambda console](https://console.aws.amazon.com/lambda/).
2. Click **Create function**.
3. Choose **Author from scratch**.
4. Set the function name to `summarizeData`.
5. Set the runtime to **Python 3.12**.
6. Under **Code source**, click **Upload from** and select the `summarizeData.py` file from the `lambda/` folder in the repository.
7. Set the handler to `lambda_handler`.
8. Go to **Configuration** > **Environment variables** and add:
   - `UPLOAD_BUCKET`: Your bucket name (e.g., `my-model-evaluation`)
   - `AUTO_DELETE`: `1`
   - `BEDROCK_TEMP`: `0.7`
   - `MAX_TOKENS`: `300`
9. Under **Execution role**, select **Use an existing role** and choose `summarizeDataRole`.
10. Click **Create function**.

### Create modelJudge Lambda
1. Repeat the above steps for the `modelJudge` function.
2. Set the function name to `modelJudge`.
3. Upload the `modelJudge.py` file.
4. Set the handler to `lambda_handler`.
5. Add environment variables:
   - `UPLOAD_BUCKET`: Your bucket name
   - `PRESIGN_TTL`: `900`
   - `UPLOAD_ACL`: `public-read` (optional, only if you want uploaded files to be publicly accessible)
6. Select the `modelJudgeRole`.
7. Click **Create function**.

## Step 4: Set up API Gateway
### Create summarizeData-API
1. Go to the [API Gateway console](https://console.aws.amazon.com/apigateway/).
2. Click **Create API** > **REST API** > **Build**.
3. Name it `summarizeData-API` and set the endpoint type to **Regional**.
4. Click **Create API**.
5. In the **Resources** section, click **Actions** > **Create Resource**.
6. Name the resource `summerizeData` and enable **CORS**.
7. Under `/summerizeData`, create methods:
   - **GET**: Integrate with the `summarizeData` Lambda function.
   - **POST**: Integrate with the `summarizeData` Lambda function.
   - **OPTIONS**: Add for CORS support.
8. Create another resource under `/summerizeData` named `presign` with a **GET** method integrated with `summarizeData`.
9. Click **Actions** > **Deploy API**, select a stage (e.g., `prod`), and note the invoke URL.

   ![API Gateway summarizeData Configuration](screenshots/api_gateway_summarize.png)

10. Enable CORS for the API:
    - Click **Actions** > **Enable CORS**.
    - Set **Access-Control-Allow-Origin** to `*` or your S3 website endpoint.
    - Deploy the API again.

### Create modelJudge-API
1. Create another API named `modelJudge-API`.
2. Create a resource `/modelJudge` with **POST** and **OPTIONS** methods integrated with the `modelJudge` Lambda function.
3. Create a resource `/modelJudge/presign` with **GET** and **OPTIONS** methods integrated with `modelJudge`.
4. Deploy the API to a stage (e.g., `prod`) and note the invoke URL.

   ![API Gateway modelJudge Configuration](screenshots/api_gateway_modeljudge.png)

5. Enable CORS as above.

## Step 5: Upload Frontend to S3
1. Go to the S3 console and select your bucket.
2. Click **Upload**.
3. Select the `index.html` file from the `frontend/` folder in the repository.
4. Upload it to the root of the bucket.

## Step 6: Test the Application
1. Access your S3 website using the website endpoint (e.g., `http://my-model-evaluation.s3-website-us-east-1.amazonaws.com`).
2. Test the application:
   - Upload a CSV file.
   - Select columns to summarize and choose summarizer models.
   - View the summaries.
   - Select judge models and evaluation metrics.
   - View the evaluation results.

## Troubleshooting
- **Presign Error in modelJudge**: If you see a "presign err," ensure the `modelJudgeRole` includes `s3:PutObjectAcl` if `UPLOAD_ACL` is set (e.g., `public-read`). Check CloudWatch logs for details.
- **API Gateway Errors**: Verify the API invoke URLs are correct in the frontend code and CORS is properly configured.
- **S3 Access Issues**: Ensure the bucket policy allows public read access for `index.html` and the IAM roles have correct S3 permissions.

## Advanced: Automated Deployment
For users familiar with AWS CLI, you can use a CloudFormation or AWS SAM template (in the `infrastructure/` folder) to automate deployment. See the repository for details.