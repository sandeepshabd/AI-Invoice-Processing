# get all stack buckets
aws cloudformation list-stack-resources \
  --stack-name "$STACK" --region "$REG" --profile "$PROF" \
  --query 'StackResourceSummaries[?ResourceType==`AWS::S3::Bucket`].PhysicalResourceId' \
  --output text > /tmp/buckets.txt || true

for BKT in $(cat /tmp/buckets.txt); do
  echo "==> Cleaning bucket: $BKT"

  # suspend versioning to stop new versions
  aws s3api put-bucket-versioning \
    --bucket "$BKT" --versioning-configuration Status=Suspended \
    --region "$REG" --profile "$PROF" || true

  # abort multipart uploads
  aws s3api list-multipart-uploads --bucket "$BKT" \
    --region "$REG" --profile "$PROF" \
    --query 'Uploads[].{Key:Key,UploadId:UploadId}' --output text 2>/dev/null | while read -r KEY UPID; do
      [ -z "$KEY" ] && continue
      aws s3api abort-multipart-upload --bucket "$BKT" --key "$KEY" --upload-id "$UPID" \
        --region "$REG" --profile "$PROF" || true
    done

  # delete all versions (batching via 1000-object chunks)
  while :; do
    aws s3api list-object-versions --bucket "$BKT" \
      --region "$REG" --profile "$PROF" \
      --query 'Versions[].{Key:Key,VersionId:VersionId}' --output text > /tmp/vers.txt 2>/dev/null || true
    aws s3api list-object-versions --bucket "$BKT" \
      --region "$REG" --profile "$PROF" \
      --query 'DeleteMarkers[].{Key:Key,VersionId:VersionId}' --output text > /tmp/marks.txt 2>/dev/null || true
    cat /tmp/vers.txt /tmp/marks.txt | sed '/^$/d' > /tmp/allv.txt
    [ ! -s /tmp/allv.txt ] && break
    split -l 1000 /tmp/allv.txt /tmp/chunk_ || true
    for f in /tmp/chunk_*; do
      [ -e "$f" ] || continue
      python3 - "$BKT" "$REG" "$PROF" "$f" <<'PY'
import sys, json, subprocess, pathlib
bkt, reg, prof, path = sys.argv[1:]
objs=[]
for line in pathlib.Path(path).read_text().splitlines():
    key, vid = line.split("\t", 1)
    objs.append({"Key": key, "VersionId": vid})
if objs:
    open("/tmp/del.json","w").write(json.dumps({"Objects":objs,"Quiet":True}))
    subprocess.run(["aws","s3api","delete-objects","--bucket",bkt,"--delete","file:///tmp/del.json","--region",reg,"--profile",prof], check=False)
PY
      rm -f "$f"
    done
    rm -f /tmp/chunk_*
  done

  # safety: remove any current objects (for non-versioned buckets)
  aws s3 rm "s3://$BKT" --recursive --region "$REG" --profile "$PROF" || true

  # delete bucket
  aws s3api delete-bucket --bucket "$BKT" --region "$REG" --profile "$PROF" || true
done
