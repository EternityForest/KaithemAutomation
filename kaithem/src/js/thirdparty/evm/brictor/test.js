var y0 = 0.3,
	z0 = 0.2;

var x0 = 0.2;
// use newton's method to figure out the initial zero
for(var i = 0; i < 10; i++){
    // console.log(x0, g(x0, y0, z0), dgdx(x0, y0, z0))
    x0 -= g(x0, y0, z0) / dgdx(x0, y0, z0)
}


console.log('f', f(x0, y0, z0))
console.log('g', g(x0, y0, z0))

function move(x, y, z, dx, df){
	return [
		y + dx * dydx(x, y, z) / 2 + df / dfdy(x, y, z) / 2,
		z + dx * dzdx(x, y, z) / 2 + df / dfdz(x, y, z) / 2
	]
}

var nyz = move(x0, y0, z0, -0.05, -0.1),
	ny = nyz[0],
	nz = nyz[1]

console.log('g', g(x0 +0.05, ny, nz))
console.log('f', f(x0 +0.05, ny, nz))


