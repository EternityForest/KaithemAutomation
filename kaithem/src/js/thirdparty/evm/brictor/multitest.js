var y0 = 0.2,
	z0 = 0.6;

var minima;

// sample a particular range of x values
// and calculate its derivatives looking for
// a sign change, and do newton's method
// to find a more precise value for each
// local minimum
function findMinima(start, end, step){
	var iterations = 5;
	var minima = [], lgs = 0;
	for(var i = start; i < end; i += step){
		var ngs = g(i, y0, z0)
		// search for a sign change
		if((lgs > 0 && ngs < 0) || (lgs < 0 && ngs > 0)){
			var x0 = newtonsMethod(i - step / 2, iterations);
			if(x0 > i - step && x0 < i) minima.push(x0);
		}
	    lgs = ngs
	}
	return minima
}

function newtonsMethod(x0, iterations){
	// use newtons method to refine the x0
	for(var j = 0; j < iterations; j++){
		x0 -= g(x0, y0, z0) / dgdx(x0, y0, z0)
	}
	return x0
}

// run newton's method on all minima
function updateMinima(){
    var iterations = 2;
    // a few iterations of newton's method
    for(var i = 0; i < minima.length; i++){
    	minima[i] = newtonsMethod(minima[i], iterations)
    }
}

// takes in a variable number of arguments which
// are 2-tuples representing a rational number
// with numerator and denominator
// it finds the things which don't have zero 
// denominator and then adds the fractions together
// and weights it by the number of terms

function addrat(){
	var epsilon = 1e-5;
	var safe = [].slice.call(arguments, 0).filter(function(rat){
		// check that denominator is nonzero
		return Math.abs(rat[1]) > epsilon
	})
	var total = 0;
	safe.map(function(rat){
		return rat[0] / rat[1]
	}).forEach(function(num){
		total += num / safe.length
	})
	return total
}


// this is the main piece that does gradient ascent
function push(x, y, z, dx, df){
	var dg = dx * dgdx(x,y,z)
	
	var ny = y + addrat([dg, dgdy(x,y,z)], [df, dfdy(x,y,z)]),
		nz = z + addrat([dg, dgdz(x,y,z)], [df, dfdz(x,y,z)])

	return [ny, nz]
}


// do a series of small steps to try and shift a particular
// minima toward a new spot

function move(i, tx, ty){
    var step = 0.01

    for(var k = 0; k < 20; k++){ // do at most 20 iterations
        var x0 = minima[i];
        var dx = x0 - tx,
            dy = ty - f(x0, y0, z0);    
        var mag = Math.sqrt(dx * dx + dy * dy)
        if(mag < step) break;
        var nyz = push(x0, y0, z0, 
            dx / mag * step, 
            dy / mag * step)
        
        y0 = nyz[0]
        z0 = nyz[1]

        updateMinima()
    }
}
