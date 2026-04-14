function EmberMushroom(myPrice, myQty) {
    let bids = {
        20: 43000,
        19: 17000,
        18: 6000,
        17: 5000,
        16: 10000,
        15: 5000,
        14: 10000,
        13: 7000,
    };

    let asks = {
        12: 20000,
        13: 25000,
        14: 35000,
        15: 6000,
        16: 5000,
        17: 0,
        18: 10000,
        19: 12000,
    };

    let buyback = 20;
    let fee = 0.1;

    let newBids = {};
    for (let p in bids) newBids[p] = bids[p];
    newBids[myPrice] = (newBids[myPrice] || 0) + myQty;

    let prices = [];
    for (let p in newBids) prices.push(Number(p));
    for (let p in asks) prices.push(Number(p));

    prices = [...new Set(prices)].sort(function (a, b) {
        return a - b;
    });

    let clearingPrice = 0;
    let bestVolume = -1;

    for (let i = 0; i < prices.length; i++) {
        let p = prices[i];

        let bidVol = 0;
        for (let bp in newBids) {
            if (Number(bp) >= p) bidVol += newBids[bp];
        }

        let askVol = 0;
        for (let ap in asks) {
            if (Number(ap) <= p) askVol += asks[ap];
        }

        let traded = Math.min(bidVol, askVol);

        if (traded > bestVolume || (traded === bestVolume && p > clearingPrice)) {
            bestVolume = traded;
            clearingPrice = p;
        }
    }

    let supply = 0;
    for (let ap in asks) {
        if (Number(ap) <= clearingPrice) supply += asks[ap];
    }

    let ahead = 0;
    for (let bp in bids) {
        if (Number(bp) > myPrice) ahead += bids[bp];
    }
    if (bids[myPrice]) ahead += bids[myPrice];

    let fill = 0;
    if (myPrice >= clearingPrice) {
        fill = Math.min(myQty, Math.max(0, supply - ahead));
    }

    let netProfit = fill * (buyback - clearingPrice - fee);

    console.log("Clearing Price:", clearingPrice);
    console.log("Total Traded Volume:", bestVolume);
    console.log("Your Fill:", fill);
    console.log("Net Profit:", netProfit.toFixed(2));
}

EmberMushroom(20, 24000);
