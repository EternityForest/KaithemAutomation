
// line chart based on http://bl.ocks.org/mbostock/3883245
var margin = {
        top: 20,
        right: 20,
        bottom: 30,
        left: 50
    },
    width = 960 - margin.left - margin.right,
    height = 500 - margin.top - margin.bottom;

var svg = d3.select("body").append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");


var data = [];
for(var i = 0; i < 5; i += 0.01){
    data.push({ q: i, p: f(i, y0, z0) })
}



var x = d3.scale.linear() .range([0, width]);
var y = d3.scale.linear() .range([height, 0]);
// x.domain(d3.extent(data, function(d) { return d.q; }));
// y.domain(d3.extent(data, function(d) { return d.p; }));
x.domain([0, Math.PI])
y.domain([0, 1])


var xMini = d3.scale.linear() .range([0, 200]);
var yMini = d3.scale.linear() .range([0, 200]);

var xAxisMini = d3.svg.axis()
    .scale(xMini)
    .orient("top");

var yAxisMini = d3.svg.axis()
    .scale(yMini)
    .orient("left");


svg.append("g")
    .attr("class", "x axis")
    .attr("transform", "translate(700,0)")
    .call(xAxisMini);

svg.append("g")
    .attr("transform", "translate(700,000)")
    .attr("class", "y axis")
    .call(yAxisMini);



var alphaBeta = svg.append('circle')
    .attr('r', 5)
    .attr('fill', 'maroon')
    .attr("transform", "translate(700,000)")
    .attr('cx', xMini(y0))
    .attr('cy', yMini(z0))
    .call(d3.behavior.drag().on('drag', changeAlphaBeta))



var xAxis = d3.svg.axis()
    .scale(x)
    .orient("bottom");

var yAxis = d3.svg.axis()
    .scale(y)
    .orient("left");

var line = d3.svg.line()
    .x(function(d) { return x(d.q); })
    .y(function(d) { return y(d.p); });




svg.append("g")
    .attr("class", "x axis")
    .attr("transform", "translate(0," + height + ")")
    .call(xAxis);

svg.append("g")
    .attr("class", "y axis")
    .call(yAxis);

var plot = svg.append("path")
    .datum(data)
    .attr("class", "line")
    .attr("d", line);


var realcircle = svg.append('circle')
    .attr('r', 15)
    .attr('fill', 'green')
    .attr('cx', x(x0))
    .attr('cy', y(f(x0, y0, z0)))
    .call(d3.behavior.drag().on('drag', change))



var xAxis = d3.svg.axis()
    .scale(x)
    .orient("bottom");

var yAxis = d3.svg.axis()
    .scale(y)
    .orient("left");



function changeAlphaBeta(){
    y0 = xMini.invert(d3.event.x-700)
    z0 = yMini.invert(d3.event.y)

    for(var i = 0; i < 10; i++){
        x0 -= g(x0, y0, z0) / dgdx(x0, y0, z0)
    }

    updatePlots()
}


function change(){
    var target = d3.select(this)
    target
        .attr('cx', d3.event.x)
        .attr('cy', d3.event.y)

    for(var k = 0; k < 40; k++){ // do a max of 20 iterations
        var dx = x0 - x.invert(d3.event.x),
            dy = y.invert(d3.event.y) - f(x0, y0, z0);

        var step = 0.01
        var mag = Math.sqrt(dx * dx + dy * dy)
        if(mag < step) break;

        var nyz = move(x0, y0, z0, 
            dx / mag * step, 
            dy / mag * step)
    
        y0 = nyz[0]
        z0 = nyz[1]
        // a single iteration of newton's method
        x0 -= g(x0, y0, z0) / dgdx(x0, y0, z0)
    }
    updatePlots()
}


function updatePlots(){
    if(isNaN(x0) || isNaN(y0) || isNaN(z0)){
        y0 = 0.568
        z0 = 0.192
        x0 = 0.2
    }
    realcircle
        .attr('cx', x(x0))
        .attr('cy', y(f(x0, y0, z0)))

    alphaBeta
        .attr('cx', xMini(y0))
        .attr('cy', yMini(z0))

    var data = [];
    for(var i = 0; i < 5; i += 0.01){
        data.push({ q: i, p: f(i, y0, z0) })
    }

    plot.datum(data).attr("d", line)
}