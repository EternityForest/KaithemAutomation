function Cot(x){ return 1 / Math.tan(x) }
function Csc(x){ return 1 / Math.sin(x) }


function f(x, y, z){
	return         (-2*(y - z)*(-2 + y*z + 2*(-1 + y)*(-1 + z)*Math.cos(x))*   Math.pow(Math.sin(x/2.),2)   )/
     -  ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x)))
}
// the following code wouldn't be necessary if we had cool automatic differnetiation

function dfdy(x, y, z){
	return        (2*(2 + y*(-1 + z) - z + (-2 + y + z)*Math.cos(x))*
	    Math.sqrt((Math.pow(y - z, 2)*Math.pow(Math.sin(x/2), 2))/
	      ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x))))
	    )/((y - z)*(2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x)))
}

function dfdz(x, y, z){
	return       (-2*(2 + y*(-1 + z) - z + (-2 + y + z)*Math.cos(x))*
	    Math.sqrt((Math.pow(y - z, 2)*Math.pow(Math.sin(x/2), 2))/
	      ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x))))
	    )/((y - z)*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x)))
}

function g(x, y, z){ // dfdx
return ((6*(-1 + z) + y*(6 + z*(-6 + y*z)) + 8*(-1 + y)*(-1 + z)*Math.cos(x) - 
      2*(-1 + y)*(-1 + z)*Math.cos(2*x))*Cot(x/2.)*   Math.pow(Csc(x/2.),2)   *
    Math.pow((    Math.pow(y - z, 2)      *   Math.pow(Math.sin(x/2.),2)   )/
       ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x)))
       ,1.5))/    Math.pow(y - z,2)      
}

function dgdx(x, y, z){
	return (   Math.pow(Csc(x/2.),2)  *Math.sqrt((Math.pow(y-z,2)*Math.pow(Math.sin(x/2),2))/
      ((2 - 2*y + Math.pow(y,2) + 2*(-1 + y)*Math.cos(x))*(2 - 2*z + Math.pow(z,2) + 2*(-1 + z)*Math.cos(x))))
     *((-2 + 2*y - Math.pow(y,2) - 2*(-1 + y)*Math.cos(x))*(2 - 2*z + Math.pow(z,2) + 2*(-1 + z)*Math.cos(x))*
       (-6 + 6*y + 6*z - 6*y*z + Math.pow(y,2)*Math.pow(z,2) + 8*(-1 + y)*(-1 + z)*Math.cos(x) - 
         2*(-1 + y)*(-1 + z)*Math.cos(2*x)) - 
      2*Math.pow(Math.cos(x/2),2)*(2 - 2*y + Math.pow(y,2) + 2*(-1 + y)*Math.cos(x))*
       (2 - 2*z + Math.pow(z,2) + 2*(-1 + z)*Math.cos(x))*
       (-6 + 6*y + 6*z - 6*y*z + Math.pow(y,2)*Math.pow(z,2) + 8*(-1 + y)*(-1 + z)*Math.cos(x) - 
         2*(-1 + y)*(-1 + z)*Math.cos(2*x)) + 
      3*Math.pow(Math.cos(x/2),2)*   Math.pow(-6 + 6*y + 6*z - 6*y*z + Math.pow(y,2)*Math.pow(z,2) + 
          8*(-1 + y)*(-1 + z)*Math.cos(x) - 2*(-1 + y)*(-1 + z)*Math.cos(2*x), 2) - 
      16*(-1 + y)*(-1 + z)*(2 - 2*y + Math.pow(y,2) + 2*(-1 + y)*Math.cos(x))*
       (2 - 2*z + Math.pow(z,2) + 2*(-1 + z)*Math.cos(x))*Math.pow(Math.sin(x/2),2)*   Math.pow(Math.sin(x),2)  ))/
  (2.*  Math.pow(2 - 2*y + Math.pow(y,2) + 2*(-1 + y)*Math.cos(x),2)*
    Math.pow(2 - 2*z + Math.pow(z,2) + 2*(-1 + z)*Math.cos(x),2)   )

}

function dgdy(x, y, z){
	   return ((y - z)*(-20 + 2*y*(15 + y - 3*Math.pow(y,2)) + 30*z + 2*y*(-29 + y*(5 + 3*y))*z - 
	      (10 + y*(-28 + 3*y*(2 + y)))*Math.pow(z,2) + y*(-4 + y + Math.pow(y,2))*Math.pow(z,3) + 
	      (15*(-2 + z)*(-1 + z) + Math.pow(y,3)*(8 + z*(-8 + 3*z)) - 
	         Math.pow(y,2)*(1 + z*(15 + (-10 + z)*z)) + y*(-45 + z*(84 + z*(-39 + 4*z))))*
	       Math.cos(x) - 2*(-1 + z)*(3*(-2 + z) - y*(-9 + y + Math.pow(y,2) + 6*z - 2*y*z))*
	       Math.cos(2*x) - (-1 + y)*(-1 + z)*(-2 + y + z)*Math.cos(3*x))*Math.sin(x))/
	  (2.*Math.pow(2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x), 3)*
	    Math.pow(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x), 2)*
	    Math.sqrt((   Math.pow(y - z,2)   *   Math.pow(Math.sin(x/2.),2) )/
	      ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x))))
	    )
}

function dgdz(x, y, z){
	 return ((y - z)*(10*(-2 + y)*(-1 + y) + 2*(-3 + y)*(5 + 2*(-4 + y)*y)*z - 
	      (2 + y*(10 + (-6 + y)*y))*Math.pow(z,2) - (-6 + y*(6 + (-3 + y)*y))*Math.pow(z,3) + 
	      (-15*(-2 + y)*(-1 + y) + (45 + y*(-84 + (39 - 4*y)*y))*z + 
	         (1 + y*(15 + (-10 + y)*y))*Math.pow(z,2) + (-8 + (8 - 3*y)*y)*Math.pow(z,3))*Math.cos(x) + 
	      2*(-1 + y)*(-6 + 9*z - Math.pow(z,2)*(1 + z) + y*(3 + 2*(-3 + z)*z))*Math.cos(2*x) + 
	      (-1 + y)*(-1 + z)*(-2 + y + z)*Math.cos(3*x))*Math.sin(x))/
	  (2.*   Math.pow(2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x), 2)*
	    Math.pow(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x), 3)  *
	    Math.sqrt((    Math.pow(y - z,2)    *   Math.pow(Math.sin(x/2.),2)  )/
	      ((2 + (-2 + y)*y + 2*(-1 + y)*Math.cos(x))*(2 + (-2 + z)*z + 2*(-1 + z)*Math.cos(x))))
	    )
}

function dydx(x, y, z){
	return dgdx(x, y, z) / dgdy(x, y, z)
}

function dzdx(x, y, z){
	return dgdx(x, y, z) / dgdz(x, y, z)
}
