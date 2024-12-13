function useBlankDescriptions(l, additional) {
    var l2 = [];
    for (var i in l) {
        l2.push([i, '']);
    }
    if (additional) {
        for (var i in additional) {
            l2.push([i, additional[i]]);

        }
    }
    return l2;
}


function formatInterval(seconds) {
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds - (hours * 3600)) /
        60);
    var seconds = seconds - (hours * 3600) - (minutes * 60);
    var tenths = Math.floor((seconds - Math.floor(seconds)) *
        10);
    seconds = Math.floor(seconds);

    var time = "";

    time = ("" + hours).padStart(2, '0') + ":" + ("" + minutes).padStart(2, '0') + ":" + ("" + seconds).padStart(2, '0')
    return time;
}

function dictView(dict, sorts, filterf, page) {
    //Given a dict  and a list of sort keys sorts,
    //return a list of [key,value] pairs sorted by the sort
    //keys. Earlier sort keys take precendence.

    // the lowest precedence sort key is the actual dict key.

    //Keys starting with ! are interpreted as meanng to sort in descending order

    var o = []
    for (var i in dict) {
        o.push([i, dict[i]]);
    }

    const usePages = page !== undefined
    page = page || 0
    var toSkip = page * 50


    var l = []
    for (var i of sorts) {
        //Convert to (reverse, string) tuple where reverse is -1 if str started with an exclamation point
        //Get rid of the fist char if so
        l.push([
            i[0] == '!' ? -1 : 1,
            i[0] == "!" ? i.slice(1) : i
        ])
    }

    o.sort(function (a, b) {
        //For each of the possible soft keys, check if they
        //are different. If so, compare and possible reverse the ouptut


        for (var i of l) {
            var d = a[1]
            var d2 = b[1]
            var key = i[1]
            var rev = i[0]

            for (var k of key.split(".")) {
                if (d == undefined || d2 == undefined) {
                    break;
                }
                d = d[k]
                d2 = d2[k]
            }
            if (!(d == d2)) {
                return (d > d2 ? 1 : -1) * rev
            }

        }
        // Fallback sort is the keys themselves
        if (a[0] != b[0]) {
            return (a[0] > b[0]) ? 1 : -1
        }
        return 0
    });

    let o2 = []

    for (var i of o) {
        if (filterf == undefined || filterf(i[0], dict[i[0]])) {
            toSkip -= 1

            if (toSkip > 0) {
                continue
            }
            else {
                // overlap between pages
                if (toSkip < -60) {
                    if (usePages) {
                        continue
                    }
                }
                o2.push(i)
            }
        }
    }

    return (o2)
}

export { useBlankDescriptions, dictView, formatInterval }