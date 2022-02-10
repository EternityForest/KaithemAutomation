function f(x, y, z){
	return 7 * (Math.pow(y, x) - Math.pow(z, x))
}
// the following code wouldn't be necessary if we had cool automatic differnetiation

function dfdy(x, y, z){
	return 7 * x * Math.pow(y, -1 + x)
}

function dfdz(x, y, z){
	return -7 * x * Math.pow(y, -1 + x)
}

function g(x, y, z){ // dfdx
	return 7 * (Math.pow(y, x) * Math.log(y) - Math.pow(z, x) * Math.log(z))
	     
}

function dgdx(x, y, z){
	return 7 * (Math.pow(y, x) * Math.pow(Math.log(y), 2) - Math.pow(z, x) * Math.pow(Math.log(z), 2))

}

function dgdy(x, y, z){
	return 7 * (Math.pow(y, x-1) + x * Math.pow(y, x - 1) * Math.log(y))
}

function dgdz(x, y, z){
	return 7 * (-Math.pow(z, -1+x) - x * Math.pow(z, -1 + x) * Math.log(z))
}

function dydx(x, y, z){
	return dgdx(x, y, z) / dgdy(x, y, z)
}

function dzdx(x, y, z){
	return dgdx(x, y, z) / dgdz(x, y, z)
}
