# LLM Summariser Evaluator

This project allows users to upload CSV data, select columns to summarize, choose summarizer models, and evaluate the summaries using judge models. It uses AWS services: S3 for hosting the frontend, Lambda for backend processing, and API Gateway for exposing the Lambda functions.

## Requirements
- An AWS account with permissions for S3, Lambda, API Gateway, and IAM.
- Basic familiarity with the AWS Management Console (or follow the detailed setup guide).

## Setup
For detailed step-by-step instructions, see [setup_guide.md](docs/setup_guide.md).

## Usage
1. Access the static website hosted on S3.
2. Upload CSV data.
3. Select columns to summarize.
4. Choose summarizer models.
5. View summaries.
6. Select judge models.
7. Choose evaluation metrics.
8. View evaluation results.

## Contributors
- [Your Name](your-github-profile)

## License
[MIT License](https://choosealicense.com/licenses/mit/)