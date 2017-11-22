# Overview
This repo creates a CloudWatch dashboard for monitoring the health of pipelines in CodePipeline.

# Prerequisites
You must have an S3 bucket available for staging the Lambda function.   You can create one with:

```
aws s3 mb <bucket-name>
```

# Deploying
To deploy in your own account, run:

```
make deploy BUCKET_NAME=<bucket-name>
```

# Removing
To remove from your account, run:

```
make undeploy
```
