#!/bin/bash

TRADER=$1
ROUND=$2
DAY=$3

cp round_1/$TRADER /home/rujul/projects/testing/prosperity_rust_backtester/traders/$TRADER
sleep 1

docker run --rm \
-v $(pwd)/prosperity_rust_backtester/traders:/app/traders \
rust-backtester \
/app/target/release/rust_backtester \
--trader traders/$TRADER \
--dataset datasets/$ROUND \
--day=$DAY \
--output-root outputs