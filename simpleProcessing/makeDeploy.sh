# load .env so Make sees your vars (if you aren’t using the include trick yet)
set -a; source .env; set +a
printf '%q\n' "$DAILY_BATCH_CRON"
# Expect: cron\(0\ 1\ \*\ \*\ \?\ \*\)


make build
make deploy
