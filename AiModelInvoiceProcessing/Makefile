include .env
export $(shell sed 's/=.*//' .env)

build:
	sam build

deploy: build
	sam deploy --guided --debug 



outputs:
	aws cloudformation describe-stacks \
	  --stack-name $(STACK_NAME) \
	  --query "Stacks[0].Outputs"

# -------- Teardown --------
destroy:
	@echo "⚠️  Emptying buckets $(RAW_BUCKET) and $(PROCESSED_BUCKET)..."
	-aws s3 rm s3://$(RAW_BUCKET) --recursive || true
	-aws s3 rm s3://$(PROCESSED_BUCKET) --recursive || true
	@echo "⚠️  Deleting CloudFormation stack $(STACK_NAME)..."
	-aws cloudformation delete-stack --stack-name $(STACK_NAME) || true
	@echo "⏳ Waiting for stack deletion..."
	-aws cloudformation wait stack-delete-complete --stack-name $(STACK_NAME) || true
	@echo "✅ Destroy complete."

# -------- Convenience --------
reset:
	@$(MAKE) destroy
	@$(MAKE) deploy
	@$(MAKE) outputs

# (Optional) seed today's invoices into the correct date prefix
seed:
	@echo "📥 Uploading sample invoices for today (timezone $(TIMEZONE))..."
	$(eval Y := $(shell TZ=$(TIMEZONE) date +%Y))
	$(eval M := $(shell TZ=$(TIMEZONE) date +%m))
	$(eval D := $(shell TZ=$(TIMEZONE) date +%d))
	$(eval P := invoices/raw/$(Y)/$(M)/$(D))
	aws s3 cp ./data/invoice_alpine_gmbh_eur.pdf s3://$(RAW_BUCKET)/$(P)/alpine.pdf
	aws s3 cp ./data/invoice_bluepeak_usd.pdf s3://$(RAW_BUCKET)/$(P)/bluepeak.pdf
	aws s3 cp ./data/invoice_iberia_office_eur.pdf s3://$(RAW_BUCKET)/$(P)/iberia.pdf
	aws s3 cp ./data/invoice_maple_cad.pdf s3://$(RAW_BUCKET)/$(P)/maple.pdf
	aws s3 cp ./data/invoice_northwind_gbp.pdf s3://$(RAW_BUCKET)/$(P)/northwind.pdf
	aws s3 cp ./data/invoice_papeterie_paris_eur.pdf s3://$(RAW_BUCKET)/$(P)/paris.pdf
	@echo "✅ Seeded to s3://$(RAW_BUCKET)/$(P)/"


ls-raw:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval STACK := $(shell sed -n 's/stack_name = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval RAW := $(shell aws cloudformation describe-stacks --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --query "Stacks[0].Parameters[?ParameterKey=='RawBucketName'].ParameterValue|[0]" --output text))
	$(eval Y := $(shell TZ=America/Chicago date +%Y))
	$(eval M := $(shell TZ=America/Chicago date +%m))
	$(eval D := $(shell TZ=America/Chicago date +%d))
	$(eval P := invoices/raw/$(Y)/$(M)/$(D))
	aws s3 ls s3://$(RAW)/$(P)/ --recursive --human-readable --summarize --region "$(REGION)" --profile "$(PROFILE)"

ls-processed:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval STACK := $(shell sed -n 's/stack_name = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROC := $(shell aws cloudformation describe-stacks --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --query "Stacks[0].Parameters[?ParameterKey=='ProcessedBucketName'].ParameterValue|[0]" --output text))
	$(eval Y := $(shell TZ=America/Chicago date +%Y))
	$(eval M := $(shell TZ=America/Chicago date +%m))
	$(eval D := $(shell TZ=America/Chicago date +%d))
	aws s3 ls s3://$(PROC)/invoices/processed/$(Y)/$(M)/$(D)/ --recursive --human-readable --summarize --region "$(REGION)" --profile "$(PROFILE)"

ddb-list:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	aws dynamodb scan --table-name Invoices --max-items 10 --region "$(REGION)" --profile "$(PROFILE)" --output table


invoke-batch:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	aws lambda invoke --function-name "$$(aws cloudformation describe-stack-resource \
	  --stack-name $(STACK_NAME) --logical-resource-id DailyBatchFn \
	  --region "$(REGION)" --profile "$(PROFILE)" \
	  --query 'StackResourceDetail.PhysicalResourceId' --output text)" \
	  --log-type Tail /tmp/out.json --region "$(REGION)" --profile "$(PROFILE)" \
	  --query 'LogResult' --output text | base64 --decode; echo; cat /tmp/out.json
