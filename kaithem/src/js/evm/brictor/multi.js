// line chart based on http://bl.ocks.org/mbostock/3883245
var margin = { top: 20, right: 20, bottom: 30, left: 50 },
    width = 1000 - margin.left - margin.right,
    height = 500 - margin.top - margin.bottom;

var svg = d3.select("body").append("svg")
    .attr("width", width + margin.left + margin.right)
    .attr("height", 500 + height + margin.top + margin.bottom)
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

var x = d3.scale.linear().range([0, width]);
var y = d3.scale.linear().range([height, 0]);
x.domain([0, 7])
y.domain([0, 1.1])

var xMini = d3.scale.linear().range([0, 200]);
var yMini = d3.scale.linear().range([0, 200]);
var xAxisMini = d3.svg.axis().scale(xMini).orient("top");
var yAxisMini = d3.svg.axis().scale(yMini).orient("left");

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

var xAxis = d3.svg.axis().scale(x).orient("bottom");
var yAxis = d3.svg.axis().scale(y).orient("left");
var line = d3.svg.line()
    .x(function(d) { return x(d.q); })
    .y(function(d) { return y(d.p); });

svg.append("g").attr("class", "x axis")
    .attr("transform", "translate(0," + height + ")")
    .call(xAxis);
svg.append("g").attr("class", "y axis").call(yAxis);

var plot = svg.append("path").attr("class", "line");

var xAxis = d3.svg.axis().scale(x).orient("bottom");
var yAxis = d3.svg.axis().scale(y).orient("left");

updatePlots()

function multichange(d, i){
    if(typeof minima[i] == 'undefined') return;
    move(i, x.invert(d3.event.x), y.invert(d3.event.y))
    updatePlots()
}


function changeAlphaBeta(){
    y0 = xMini.invert(d3.event.x-700)
    z0 = yMini.invert(d3.event.y)
    updateMinima()
    updatePlots()
}


function updatePlots(){
    alphaBeta
        .attr('cx', xMini(y0))
        .attr('cy', yMini(z0))
    var data = [];
    for(var i = 0; i < 7; i += 0.01){
        data.push({ q: i, p: f(i, y0, z0) })
    }

    plot.datum(data).attr("d", line)
    minima = findMinima(0, 8, 0.01)

    var wumbo = svg.selectAll('.wumbo').data(minima)
    wumbo.enter()
        .append('circle')
        .attr('class', 'wumbo')
        .attr('r', 10)
        .attr('fill', 'orange')
        .call(d3.behavior.drag().on('drag', multichange))
    wumbo
        .attr('cx', function(d, i){ return x(d) })
        .attr('cy', function(d, i){ return y(f(d, y0, z0)) })
    wumbo.exit().remove()
}