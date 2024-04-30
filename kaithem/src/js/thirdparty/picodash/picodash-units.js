/* MIT License by Daniel Dunn

This file requires your import map to say where to find convert.min.js or
similar: https://www.npmjs.com/package/convert
*/

import picodash from "picodash"
import convert from "convert";

class UnitConvert extends picodash.Filter {
    constructor(s, cfg, prev) {
        super(s, cfg, prev)
        this.unit = this.args[0]

        if (prev && prev.config.unit) {
            this.prevUnit = prev.config.unit
            this.config.unit = this.unit
        }


        // If the previous data has a unit, convert all the range params.
        // If not, keep range params.

        for (const i of ['min', 'max', 'high', 'low', 'step']) {
            if (typeof prev.config[i] !== 'undefined') {
                if (prev && prev.config.unit) {
                    convert(prev.config[i], prev.config.unit).to(this.unit)
                }
                else {
                    this.config[i] = prev.config[i]
                }
            }
        }

    }

    async get(unfiltered) {
        if (this.prevUnit) {
            return convert(parseFloat(unfiltered), this.prevUnit).to(this.unit)
        }
        else {
            return unfiltered
        }
    }

    async set(val) {
        if (this.prevUnit) {
            return convert(parseFloat(val), this.unit).to(this.prevUnit)
        }
        else {
            return val
        }
    }
}

picodash.addFilterProvider('unit', UnitConvert)
