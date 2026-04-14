function DryLandFlax(myPrice, myQty) {
    let bids = { 30: 30000, 29: 5000, 28: 12000, 27: 28000 };
    let asks = { 28: 40000, 31: 20000, 32: 20000, 33: 30000 };
    let buyback = 30;

    // add your order
    let newBids = {};
    for (let p in bids) newBids[p] = bids[p];
    newBids[myPrice] = (newBids[myPrice] || 0) + myQty;
    // console.log("New Bids:", newBids);

    // find clearing price
    let prices = [];
    for (let p in newBids) prices.push(Number(p));
    for (let p in asks) prices.push(Number(p));

    // in the prices array, we have all the unique prices from both sides of the book. We will iterate through them to find the clearing price that maximizes volume.
    prices = [...new Set(prices)].sort(function (a, b) {
        return a - b;
    });

    let bestPrice = 0;
    let bestVol = -1;

    for (let i = 0; i < prices.length; i++) {
        let p = prices[i];

        let bidVol = 0;

        // for each price level in the newBids, if the price is greater than or equal to p, add its volume to bidVol

        for (let bp in newBids) {
            // console.log("Checking bid price:", bp, "against", p);
            // console.log(bp, newBids[bp]);
            if (bp >= p) {
                bidVol += newBids[bp];
            }
        }

        let askVol = 0;
        for (let ap in asks) {
            if (ap <= p) {
                askVol += asks[ap];
            }
        }

        let traded = Math.min(bidVol, askVol);

        // console.log("Price:", p, "Bid Vol:", bidVol, "Ask Vol:", askVol, "Traded:", traded);
        if (traded >= bestVol || (traded === bestVol && p > bestPrice)) {
            bestVol = traded;
            bestPrice = p;
        }
    }

    // my fill
    let fill = 0;

    if (myPrice >= bestPrice) {
        let supply = 0;
        for (let ap in asks) {
            if (ap <= bestPrice) supply += asks[ap];
        }

        let ahead = 0;

        for (let bp in bids) {
            // console.log("Checking bid price:", bp, "against my price:", myPrice);
            if (Number(bp) > myPrice) {
                // console.log("Adding ahead volume:", bids[bp]);
                ahead += bids[bp];
                console.log("After adding bid:", ahead);
            }
        }
        if (bids[myPrice]) {
            ahead += bids[myPrice];
        } // you're last
        console.log("After some if statement:", ahead);

        fill = supply - ahead;
        console.log(fill, supply, ahead);
        if (fill < 0) fill = 0;

        if (fill > myQty) fill = myQty;
    }

    let profit = fill * (buyback - bestPrice);

    console.log("Clearing Price:", bestPrice);
    console.log("Total Volume:", bestVol);
    console.log("Your Fill:", fill);
    console.log("Profit:", profit);
}

DryLandFlax(30, 9999);
