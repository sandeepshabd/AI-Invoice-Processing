#!/usr/bin/env bash
set -euo pipefail

# --- Parse basics from samconfig.toml (fallbacks if missing) ---
get_from_toml() {
  # Usage: get_from_toml keyname
  # looks for lines like: key = "value"
  sed -n 's/^[[:space:]]*'"$1"'[[:space:]]*=[[:space:]]*"\(.*\)".*/\1/p' samconfig.toml | head -1
}

STACK="${STACK:-$(get_from_toml stack_name || true)}"
REGION="${REGION:-$(get_from_toml region || true)}"
PROFILE="${PROFILE:-$(get_from_toml profile || true)}"
TIMEZONE="${TIMEZONE:-$(get_from_toml Timezone || true)}"

: "${STACK:=invoice-phase2-prod}"
: "${REGION:=us-east-1}"
: "${PROFILE:=default}"
: "${TIMEZONE:=America/Chicago}"

# --- Helpers ---
cf_fn() {
  local logical="$1"
  aws cloudformation describe-stack-resource \
    --stack-name "$STACK" \
    --logical-resource-id "$logical" \
    --region "$REGION" --profile "$PROFILE" \
    --query 'StackResourceDetail.PhysicalResourceId' --output text
}

FN_BATCH="$(cf_fn DailyBatchFn)"
FN_PROC="$(cf_fn InvoiceProcessorFn)"

usage() {
  cat <<'USAGE'
Usage: ./run.sh <command> [args]

Commands:
  info                     Show resolved stack/region/profile and both Lambda configs
  invoke                   Invoke DailyBatchFn and print tail logs + /tmp/out.json
  set-proc <bucket>        Set PROCESSED_BUCKET on DailyBatchFn
  set-llm  <true|false>    Set USE_LLM on DailyBatchFn
  set-llm-both <true|false>Set USE_LLM on BOTH Lambdas
  cold-start               Force a cold start of DailyBatchFn by toggling memory
USAGE
}

cmd="${1:-invoke}"

case "$cmd" in
  info)
    echo "Stack=$STACK Region=$REGION Profile=$PROFILE Timezone=$TIMEZONE"
    echo "FunctionName (DailyBatchFn): $FN_BATCH"
    aws lambda get-function-configuration --function-name "$FN_BATCH" \
      --region "$REGION" --profile "$PROFILE"
    echo
    echo "FunctionName (InvoiceProcessorFn): $FN_PROC"
    aws lambda get-function-configuration --function-name "$FN_PROC" \
      --region "$REGION" --profile "$PROFILE"
    ;;

  invoke)
    echo "FunctionName: $FN_BATCH"
    aws lambda invoke \
      --function-name "$FN_BATCH" \
      --log-type Tail /tmp/out.json \
      --region "$REGION" --profile "$PROFILE" \
      --query 'LogResult' --output text | base64 --decode
    echo
    cat /tmp/out.json
    ;;

  set-proc)
    PROC="${2:?Pass processed bucket name, e.g. invoices-processed--...}"
    aws lambda get-function-configuration \
      --function-name "$FN_BATCH" \
      --region "$REGION" --profile "$PROFILE" \
      --query 'Environment.Variables' --output json >/tmp/vars.json
    jq --arg proc "$PROC" '.PROCESSED_BUCKET=$proc' /tmp/vars.json | jq '{Variables:.}' >/tmp/env.json
    aws lambda update-function-configuration \
      --function-name "$FN_BATCH" \
      --environment file:///tmp/env.json \
      --region "$REGION" --profile "$PROFILE"
    ;;

  set-llm)
    VAL="${2:?true|false}"
    aws lambda get-function-configuration \
      --function-name "$FN_BATCH" \
      --region "$REGION" --profile "$PROFILE" \
      --query 'Environment.Variables' --output json >/tmp/vars.json
    jq --arg val "$VAL" '.USE_LLM=$val' /tmp/vars.json | jq '{Variables:.}' >/tmp/env.json
    aws lambda update-function-configuration \
      --function-name "$FN_BATCH" \
      --environment file:///tmp/env.json \
      --region "$REGION" --profile "$PROFILE"
    ;;

  set-llm-both)
    VAL="${2:?true|false}"
    for FN in "$FN_BATCH" "$FN_PROC"; do
      aws lambda get-function-configuration \
        --function-name "$FN" \
        --region "$REGION" --profile "$PROFILE" \
        --query 'Environment.Variables' --output json >/tmp/vars.json
      jq --arg val "$VAL" '.USE_LLM=$val' /tmp/vars.json | jq '{Variables:.}' >/tmp/env.json
      aws lambda update-function-configuration \
        --function-name "$FN" \
        --environment file:///tmp/env.json \
        --region "$REGION" --profile "$PROFILE"
    done
    ;;

  cold-start)
    CUR=$(aws lambda get-function-configuration \
      --function-name "$FN_BATCH" \
      --query 'MemorySize' --output text \
      --region "$REGION" --profile "$PROFILE")
    INC=$((CUR+1))
    aws lambda update-function-configuration \
      --function-name "$FN_BATCH" \
      --memory-size "$INC" \
      --region "$REGION" --profile "$PROFILE" >/dev/null
    aws lambda update-function-configuration \
      --function-name "$FN_BATCH" \
      --memory-size "$CUR" \
      --region "$REGION" --profile "$PROFILE" >/dev/null
    echo "Cold start triggered for $FN_BATCH"
    ;;

  *)
    usage; exit 2;;
esac
