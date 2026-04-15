docker run --rm rust-backtester /app/target/release/rust_backtester --help
chmod +x run.sh

## Raw command

'
docker run --rm \
rust-backtester \
/app/target/release/rust_backtester \
--trader traders/latest_trader.py \
--dataset datasets/round1 \
--day 0 \
--output-root outputs`
'

## Run.sh

./run.sh $PATH $DATASET $DAY
./run.sh trader.py round1 0
