#!/usr/bin/env bash
set -euo pipefail

# ==== Adjust if needed ====
REGION="us-east-1"
PROFILE="demo"
STACK="invoice-phase2-prod"
# ==========================

aws() { command aws --region "$REGION" --profile "$PROFILE" "$@"; }

echo "==> Discovering resources in stack: $STACK"

# Stack parameters (what CFN thinks the bucket names are)
RAW_PARAM=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" \
  --query "Stacks[0].Parameters[?ParameterKey=='RawBucketName'].ParameterValue|[0]" \
  --output text || echo "None")

PROC_PARAM=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" \
  --query "Stacks[0].Parameters[?ParameterKey=='ProcessedBucketName'].ParameterValue|[0]" \
  --output text || echo "None")

# Function ARNs/names from CFN logical IDs
BATCH_FN=$(aws cloudformation describe-stack-resource \
  --stack-name "$STACK" --logical-resource-id DailyBatchFn \
  --query 'StackResourceDetail.PhysicalResourceId' --output text || echo "None")

PROC_FN=$(aws cloudformation describe-stack-resource \
  --stack-name "$STACK" --logical-resource-id InvoiceProcessorFn \
  --query 'StackResourceDetail.PhysicalResourceId' --output text || echo "None")

RULE_NAME=$(aws cloudformation describe-stack-resource \
  --stack-name "$STACK" --logical-resource-id DailyBatchRule \
  --query 'StackResourceDetail.PhysicalResourceId' --output text || echo "None")

# Buckets from Lambda envs 
RAW_ENV="None"; PROC_ENV="None"
if [ "$BATCH_FN" != "None" ]; then
  RAW_ENV=$(aws lambda get-function-configuration --function-name "$BATCH_FN" \
    --query 'Environment.Variables.RAW_BUCKET' --output text || echo "None")
  PROC_ENV=$(aws lambda get-function-configuration --function-name "$BATCH_FN" \
    --query 'Environment.Variables.PROCESSED_BUCKET' --output text || echo "None")
fi

echo "RAW_PARAM=$RAW_PARAM"
echo "PROC_PARAM=$PROC_PARAM"
echo "BATCH_FN=$BATCH_FN"
echo "PROC_FN=$PROC_FN"
echo "RULE_NAME=$RULE_NAME"
echo "RAW_ENV=$RAW_ENV"
echo "PROC_ENV=$PROC_ENV"

# Build a unique list of buckets to purge
BUCKETS=$(printf "%s\n%s\n%s\n%s\n" "$RAW_PARAM" "$PROC_PARAM" "$RAW_ENV" "$PROC_ENV" \
  | sed 's/None//g;s/null//g;/^$/d' | sort -u)

# --- 1) Quiesce eventing so nothing repopulates ---

if [ -n "$RULE_NAME" ] && [ "$RULE_NAME" != "None" ]; then
  echo "==> Disabling EventBridge rule: $RULE_NAME"
  aws events disable-rule --name "$RULE_NAME" || true

  TIDS=$(aws events list-targets-by-rule --rule "$RULE_NAME" \
    --query 'Targets[*].Id' --output text || true)
  if [ -n "${TIDS:-}" ]; then
    echo "==> Removing EventBridge targets"
    aws events remove-targets --rule "$RULE_NAME" --ids $TIDS || true
  fi
fi

s3_exists() {
  aws s3api head-bucket --bucket "$1" >/dev/null 2>&1
}

# Remove S3 notifications on any discovered buckets (especially RAW) so S3 won't invoke Lambda during purge
for B in $BUCKETS; do
  if [ -n "$B" ] && s3_exists "$B"; then
    echo "   - $B"
    aws s3api put-bucket-notification-configuration \
      --bucket "$B" --notification-configuration '{}' || true
  else
    echo "   - $B (skip: not found)"
  fi
done

# --- 2) Purge S3 buckets (versions + delete markers) and delete them ---


purge_bucket() {
  local B="$1"
  if ! s3_exists "$B"; then
    echo "==> $B (skip: not found)"
    return 0
  fi
  echo "==> Purging bucket: $B"

  # delete versions & delete markers in batches
  while true; do
    OUT=$(aws s3api list-object-versions --bucket "$B" --output json || echo '{}')
    COUNT=$(echo "$OUT" | jq '[ (.Versions[]? | {Key,VersionId}), (.DeleteMarkers[]? | {Key,VersionId}) ] | length')
    [ "${COUNT:-0}" -eq 0 ] && break
    echo "$OUT" \
      | jq -c '[ (.Versions[]? | {Key,VersionId}), (.DeleteMarkers[]? | {Key,VersionId}) ]
                | [ range(0; length; 1000) as $i | {Objects: .[$i:($i+1000)], Quiet:true} ] 
                | .[]' \
      | while read -r batch; do
          aws s3api delete-objects --bucket "$B" --delete "$batch" || true
        done
  done

  # abort multipart uploads (best-effort)
  MPU=$(aws s3api list-multipart-uploads --bucket "$B" --query 'Uploads[*].[Key,UploadId]' --output text 2>/dev/null || true)
  if [ -n "${MPU:-}" ]; then
    echo "$MPU" | while read -r key uploadid; do
      aws s3api abort-multipart-upload --bucket "$B" --key "$key" --upload-id "$uploadid" || true
    done
  fi

  echo "==> Deleting bucket: $B"
  aws s3api delete-bucket --bucket "$B" || true
}

echo "Buckets to process:"
for B in $BUCKETS; do
  echo "  - ${B:-<empty>}"
done

echo "Purging buckets..."
for B in $BUCKETS; do
  purge_bucket "$B" || true
done

# --- 3) Delete the stack (should succeed now that buckets are gone) ---

echo "==> Deleting CloudFormation stack: $STACK"
aws cloudformation delete-stack --stack-name "$STACK" || true
echo "==> Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete --stack-name "$STACK" || true
echo "==> Stack deletion done (or already gone)."

# --- 4) Optional: clean Lambda log groups (ignore errors if they don't exist) ---

if [ "$BATCH_FN" != "None" ]; then
  aws logs delete-log-group --log-group-name "/aws/lambda/${BATCH_FN}" || true
fi
if [ "$PROC_FN" != "None" ]; then
  aws logs delete-log-group --log-group-name "/aws/lambda/${PROC_FN}" || true
fi

echo "Teardown complete."
