REGION := eu-central-1
BUCKET_NAME := vnr-pipeline-dashboard
STACK_NAME := tools-pipeline-dashboard

help:
	@echo "Targets:"
	@echo "    package  -- package and stage the lambda function"
	@echo "    deploy   -- deploy the lambda function"

package:
	mkdir -p .out
	aws cloudformation package --template-file template.yml --s3-bucket $(BUCKET_NAME) --output-template-file .out/template.yml

deploy: package
	aws cloudformation deploy --template-file .out/template.yml --stack-name $(STACK_NAME) --capabilities CAPABILITY_NAMED_IAM --region $(REGION)

undeploy:
	aws cloudformation delete-stack --stack-name $(STACK_NAME) --region $(REGION)


.PHONY: help package deploy undeploy
