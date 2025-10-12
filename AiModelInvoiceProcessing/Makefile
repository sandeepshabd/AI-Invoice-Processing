-include .env
export $(shell sed 's/=.*//' .env)
TIMEZONE ?= America/Chicago


build:
	rm -rf .aws-sam/build
	sam build --no-cached


deploy: build
	sam deploy \
	--stack-name invoice-phase2-prod \
	--region us-east-1 --profile demo \
	--capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
	--no-confirm-changeset   # auto-executes
 



outputs:
	aws cloudformation describe-stacks \
	  --stack-name $(STACK) \
	  --query "Stacks[0].Outputs"

# -------- Teardown --------
.ONESHELL:
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

# --- helpers to read samconfig.toml ---
region_from_toml  = $(shell sed -n 's/^[[:space:]]*region[[:space:]]*=[[:space:]]*"\(.*\)".*/\1/p' samconfig.toml | head -1)
profile_from_toml = $(shell sed -n 's/^[[:space:]]*profile[[:space:]]*=[[:space:]]*"\(.*\)".*/\1/p' samconfig.toml | head -1)
stack_from_toml   = $(shell sed -n 's/^[[:space:]]*stack_name[[:space:]]*=[[:space:]]*"\(.*\)".*/\1/p' samconfig.toml | head -1)

REGION  ?= $(region_from_toml)
PROFILE ?= $(profile_from_toml)
STACK   ?= $(stack_from_toml)

# resolve buckets from stack parameters
RAW_BUCKET  = $(shell aws cloudformation describe-stacks --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --query "Stacks[0].Parameters[?ParameterKey=='RawBucketName'].ParameterValue|[0]" --output text 2>/dev/null)
PROC_BUCKET = $(shell aws cloudformation describe-stacks --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --query "Stacks[0].Parameters[?ParameterKey=='ProcessedBucketName'].ParameterValue|[0]" --output text 2>/dev/null)



# Abort all multipart uploads (guarded)
define abort_mpus
@sh -c 'if aws s3api head-bucket --bucket "$(1)" --region "$(REGION)" --profile "$(PROFILE)" >/dev/null 2>&1; then \
  echo "• Aborting multipart uploads in $(1)..."; \
  aws s3api list-multipart-uploads --bucket "$(1)" --region "$(REGION)" --profile "$(PROFILE)" \
    --query '"'"'Uploads[].{Key:Key,Id:UploadId}'"'"' --output json \
  | jq -c '"'"'.[]?'"'"' \
  | while read -r u; do \
      KEY=$$(echo $$u | jq -r .Key); ID=$$(echo $$u | jq -r .Id); \
      aws s3api abort-multipart-upload --bucket "$(1)" --key "$$KEY" --upload-id "$$ID" \
        --region "$(REGION)" --profile "$(PROFILE)" || true; \
    done; \
else \
  echo "• (skip) $(1) does not exist"; \
fi'
endef

# Empty ALL versions + delete markers (guarded, loops until empty)
define empty_bucket_versions
@sh -c 'if aws s3api head-bucket --bucket "$(1)" --region "$(REGION)" --profile "$(PROFILE)" >/dev/null 2>&1; then \
  echo "• Emptying ALL versions & delete markers in $(1)..."; \
  while true; do \
    TMP=$$(mktemp); \
    aws s3api list-object-versions --bucket "$(1)" --max-items 1000 \
      --region "$(REGION)" --profile "$(PROFILE)" > $$TMP || true; \
    CNT_V=$$(jq '"'"'.Versions|length // 0'"'"' $$TMP); \
    CNT_M=$$(jq '"'"'.DeleteMarkers|length // 0'"'"' $$TMP); \
    if [ "$$CNT_V" -eq 0 ] && [ "$$CNT_M" -eq 0 ]; then rm -f $$TMP; break; fi; \
    jq -c '"'"'{Objects: ((.Versions//[] + .DeleteMarkers//[]) | map({Key:.Key, VersionId:.VersionId})), Quiet:true}'"'"' $$TMP \
      | aws s3api delete-objects --bucket "$(1)" --delete file:///dev/stdin \
          --region "$(REGION)" --profile "$(PROFILE)" || true; \
    rm -f $$TMP; \
  done; \
else \
  echo "• (skip) $(1) does not exist"; \
fi'
endef

# Disable S3 notifications (guarded)
define disable_s3_notifications
@sh -c 'if aws s3api head-bucket --bucket "$(1)" --region "$(REGION)" --profile "$(PROFILE)" >/dev/null 2>&1; then \
  echo "• Disabling S3 notifications on $(1)..."; \
  aws s3api put-bucket-notification-configuration \
    --bucket "$(1)" \
    --notification-configuration "{}" \
    --region "$(REGION)" --profile "$(PROFILE)" || true; \
else \
  echo "• (skip) $(1) does not exist"; \
fi'
endef

# Disable EventBridge rule (no multiline if/fi)
define disable_event_rule
@sh -c 'RULE=$$(aws cloudformation describe-stack-resource --stack-name "$(STACK)" \
  --logical-resource-id DailyBatchRule --region "$(REGION)" --profile "$(PROFILE)" \
  --query '"'"'StackResourceDetail.PhysicalResourceId'"'"' --output text 2>/dev/null || true); \
if [ -n "$$RULE" ] && [ "$$RULE" != "None" ]; then \
  echo "• Disabling EventBridge rule $$RULE..."; \
  aws events disable-rule --name "$$RULE" --region "$(REGION)" --profile "$(PROFILE)" >/dev/null 2>&1 || true; \
else \
  echo "• (skip) EventBridge rule not found"; \
fi'
endef


FN_BATCH := $(shell aws cloudformation describe-stack-resource --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --logical-resource-id DailyBatchFn --query 'StackResourceDetail.PhysicalResourceId' --output text 2>/dev/null)
FN_PROC  := $(shell aws cloudformation describe-stack-resource --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" --logical-resource-id InvoiceProcessorFn --query 'StackResourceDetail.PhysicalResourceId' --output text 2>/dev/null)

ENV_PROC_BATCH := $(shell test -n "$(FN_BATCH)" && aws lambda get-function-configuration --function-name "$(FN_BATCH)" --region "$(REGION)" --profile "$(PROFILE)" --query 'Environment.Variables.PROCESSED_BUCKET' --output text 2>/dev/null)
ENV_PROC_PROC  := $(shell test -n "$(FN_PROC)"  && aws lambda get-function-configuration --function-name "$(FN_PROC)"  --region "$(REGION)" --profile "$(PROFILE)" --query 'Environment.Variables.PROCESSED_BUCKET' --output text 2>/dev/null)

print-resolved:
	@echo "Region=$(REGION) Profile=$(PROFILE) Stack=$(STACK)"
	@echo "RawBucket(stack)=$(RAW_BUCKET)"
	@echo "ProcessedBucket(stack)=$(PROC_BUCKET)"
	@echo "ProcessedBucket(env DailyBatchFn)=$(ENV_PROC_BATCH)"
	@echo "ProcessedBucket(env InvoiceProcessorFn)=$(ENV_PROC_PROC)"


# ---- MAIN TARGETS ----

# 1) Stop writes + empty buckets
pre-destroy: print-resolved
	@echo "🔒 Draining triggers..."
	$(call disable_s3_notifications,$(RAW_BUCKET))
	$(call disable_event_rule)
	@echo "🧹 Aborting MPUs..."
	$(call abort_mpus,$(RAW_BUCKET))
	$(call abort_mpus,$(PROC_BUCKET))
	@echo "🧽 Emptying buckets (all versions + delete markers)..."
	$(call empty_bucket_versions,$(RAW_BUCKET))
	$(call empty_bucket_versions,$(PROC_BUCKET))
	@echo "✅ Buckets emptied."


# 2) Delete stack (CFN) and then delete buckets themselves, safely
# --- discover bucket names from multiple sources (stack params, lambda envs, live resources)
ALL_BUCKETS := $(strip \
  $(RAW_BUCKET) \
  $(PROC_BUCKET) \
  $(ENV_PROC_BATCH) \
  $(ENV_PROC_PROC) \
  $(shell aws cloudformation list-stack-resources --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" \
          --query "StackResourceSummaries[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text 2>/dev/null) \
)

destroy: pre-destroy
	@echo "🗑️  Deleting CloudFormation stack $(STACK)..."
	-aws cloudformation delete-stack --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" || true
	@echo "⏳ Waiting for stack deletion..."
	-aws cloudformation wait stack-delete-complete --stack-name "$(STACK)" --region "$(REGION)" --profile "$(PROFILE)" || true

	@echo "🧯 Final bucket delete (stack may have retained or failed):"
	REGION="$(REGION)"; PROFILE="$(PROFILE)"; \
	for B in $(ALL_BUCKETS); do \
	  [ "$$B" = "None" ] && continue; \
	  [ -z "$$B" ] && continue; \
	  if aws s3api head-bucket --bucket "$$B" --region "$$REGION" --profile "$$PROFILE" >/dev/null 2>&1; then \
	    echo "  - emptying & deleting $$B"; \
	    aws s3 rm "s3://$$B" --recursive --region "$$REGION" --profile "$$PROFILE" || true; \
	    while :; do \
	      TMP=$$(mktemp); \
	      aws s3api list-object-versions --bucket "$$B" --max-items 1000 --region "$$REGION" --profile "$$PROFILE" >"$$TMP" 2>/dev/null || true; \
	      CNT_V=$$(jq '.Versions|length // 0' "$$TMP"); CNT_M=$$(jq '.DeleteMarkers|length // 0' "$$TMP"); \
	      if [ "$$CNT_V" -eq 0 ] && [ "$$CNT_M" -eq 0 ]; then rm -f "$$TMP"; break; fi; \
	      jq -c '{Objects: ((.Versions//[] + .DeleteMarkers//[]) | map({Key:.Key, VersionId:.VersionId})), Quiet:true}' "$$TMP" \
	        | aws s3api delete-objects --bucket "$$B" --delete file:///dev/stdin --region "$$REGION" --profile "$$PROFILE" || true; \
	      rm -f "$$TMP"; \
	    done; \
	    aws s3api delete-bucket --bucket "$$B" --region "$$REGION" --profile "$$PROFILE" || true; \
	  else \
	    echo "  - (skip) $$B not present"; \
	  fi; \
	done
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
	$(eval REGION := $(shell sed -nE '/\[default\.deploy\.parameters\]/,$$ s/^[[:space:]]*region[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -nE '/\[default\.deploy\.parameters\]/,$$ s/^[[:space:]]*profile[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' samconfig.toml | head -1))
	$(eval STACK := $(shell sed -nE '/\[default\.deploy\.parameters\]/,$$ s/^[[:space:]]*stack_name[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' samconfig.toml | head -1))
	$(eval FN := $(shell aws cloudformation describe-stack-resource --stack-name "$(STACK)" --logical-resource-id DailyBatchFn --region "$(REGION)" --profile "$(PROFILE)" --query 'StackResourceDetail.PhysicalResourceId' --output text))
	$(eval PROC := $(shell aws lambda get-function-configuration --function-name "$(FN)" --region "$(REGION)" --profile "$(PROFILE)" --query 'Environment.Variables.PROCESSED_BUCKET' --output text))
	$(eval DATE := $(shell TZ=America/Chicago date +%Y/%m/%d))

	@echo "Region=$(REGION) Profile=$(PROFILE) Stack=$(STACK) Proc=$(PROC) Date=$(DATE)"
	@aws s3 ls "s3://$(PROC)/invoices/processed/$(DATE)/" \
	  --recursive --human-readable --summarize \
	  --region "$(REGION)" --profile "$(PROFILE)" || true


	@KEY=$$(aws s3api list-objects-v2 --bucket "$(PROC)" --prefix "invoices/processed/$(DATE)/" \
	  --query 'Contents[?ends_with(Key, `parsed.json`)].Key | [0]' --output text \
	  --region "$(REGION)" --profile "$(PROFILE)"); \
	if [ "$$KEY" != "None" ] && [ -n "$$KEY" ]; then \
	  echo "Showing: $$KEY"; \
	  aws s3 cp "s3://$(PROC)/$$KEY" - --region "$(REGION)" --profile "$(PROFILE)" | jq .; \
	else \
	  echo "No parsed.json found under invoices/processed/$(DATE)/"; \
	fi


ddb-list:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	aws dynamodb scan --table-name Invoices --max-items 10 --region "$(REGION)" --profile "$(PROFILE)" --output table


invoke-batch:
	$(eval REGION := $(shell sed -n 's/region = "\(.*\)"/\1/p' samconfig.toml | head -1))
	$(eval PROFILE := $(shell sed -n 's/profile = "\(.*\)"/\1/p' samconfig.toml | head -1))
	@set -euo pipefail; \
	FN=$$(aws cloudformation describe-stack-resource \
	  --stack-name "$(STACK)" --logical-resource-id DailyBatchFn \
	  --region "$(REGION)" --profile "$(PROFILE)" \
	  --query 'StackResourceDetail.PhysicalResourceId' --output text 2>/dev/null || true); \
	if [ -z "$$FN" ] || [ "$$FN" = "None" ]; then \
	  echo "❌ DailyBatchFn not found in stack '$(STACK)' (stack may be DELETE_COMPLETE). Redeploy or choose a live stack."; \
	  exit 2; \
	fi; \
	echo "Invoking $$FN ..."; \
	aws lambda invoke --function-name "$$FN" \
	  --log-type Tail /tmp/out.json --region "$(REGION)" --profile "$(PROFILE)" \
	  --query 'LogResult' --output text | base64 --decode; echo; cat /tmp/out.json

.PHONY: validate-one
validate-one:
	python3 "tools/validate_genai.py" "fixtures/textract_officemart.json" "fixtures/deterministic_officemart.json"
