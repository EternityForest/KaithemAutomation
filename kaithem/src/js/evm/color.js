var ctx,canvasWidth,canvasHeight;
var img_pyr;
var img_ryp;


var lowpass1, lowpass2;

function demo_app(videoWidth, videoHeight) {
    vidWidth = videoWidth
    vidHeight = videoHeight
    // canvasWidth  = canvas.width;
    // canvasHeight = canvas.height;
    ctx = canvas.getContext('2d');

    ctx.fillStyle = "rgb(0,255,0)";
    ctx.strokeStyle = "rgb(0,255,0)";

    var num_deep = 5;

    img_pyr = new color_pyr(videoWidth, videoHeight, num_deep)
    img_ryp = new color_pyr(videoWidth, videoHeight, num_deep)
    lowpass1 = new color_pyr(videoWidth, videoHeight, num_deep)
    lowpass2 = new color_pyr(videoWidth, videoHeight, num_deep)
    filtered = new color_pyr(videoWidth, videoHeight, num_deep)


}


function color_pyr(W, H, num_deep){
    function init_pyr(){
        var pyr = new jsfeat.pyramid_t(num_deep);
        pyr.allocate(W, H, jsfeat.F32_t | jsfeat.C1_t);
        return pyr;
    }
    this.levels = num_deep;
    this.W = W;
    this.H = H;
    this.Y = init_pyr();
    this.U = init_pyr();
    this.V = init_pyr();
}

color_pyr.prototype.pyrDown = function(){
    function downchan(chan){
        var i = 2, a = chan.data[0], b = chan.data[1];
        jsfeat.imgproc.pyrdown(a, b);
        for(; i < chan.levels; i++){
            a = b;
            b = chan.data[i];
            jsfeat.imgproc.pyrdown(a, b);
            // jsfeat.imgproc.pyrup(b, img_ryp.data[i - 1])
        }
    }
    downchan(this.Y);
    downchan(this.U);
    downchan(this.V);
}


color_pyr.prototype.pyrUp = function(source){
    function upchan(chan, schan){
        for(var i = 1; i < chan.levels; i++){
            jsfeat.imgproc.pyrup(schan.data[i], chan.data[i - 1])
        }
    }
    upchan(this.Y, source.Y)
    upchan(this.U, source.U)
    upchan(this.V, source.V)
}

color_pyr.prototype.lpyrUp = function(source){
    function lchan(chan, schan){
        var inner = chan.data[chan.levels - 2];
        for(var i = 0; i < inner.cols * inner.rows; i++){
            inner.data[i] = 0;
        }
        
        for(var i = chan.levels - 1; i > 0; i--){
            jsfeat.imgproc.pyrup(chan.data[i], chan.data[i - 1])
            imadd(chan.data[i - 1], schan.data[i - 1])
        }    
    }
    lchan(this.Y, source.Y)
    lchan(this.U, source.U)
    lchan(this.V, source.V)
}

color_pyr.prototype.lpyrDown = function(source){
    function lchan(chan, schan){
        for(var i = 0; i < chan.levels - 1; i++){
            imsub(schan.data[i], chan.data[i])
        }
    }
    lchan(this.Y, source.Y)
    lchan(this.U, source.U)
    lchan(this.V, source.V)
}

color_pyr.prototype.iirFilter = function(source, r){
    function iir(chan, schan){
        for(var i = 0; i < chan.levels - 1; i++){
            var lpl = chan.data[i],
                pyl = schan.data[i];
            
            for(var j = 0; j < pyl.cols * pyl.rows; j++) {
                lpl.data[j] = (1 - r) * lpl.data[j] + r * pyl.data[j];
            }
        }
    }
    iir(this.Y, source.Y)
    iir(this.U, source.U)
    iir(this.V, source.V)
}

color_pyr.prototype.setSubtract = function(a, b) {
    function subp(chan, chana, chanb){
        for(var i = 0; i < b.levels; i++){
            var al = chana.data[i],
                bl = chanb.data[i],
                cl = chan.data[i];
            for(var j = 0; j < al.cols * al.rows; j++) {
                cl.data[j] = (al.data[j] - bl.data[j])
            }
        }
    }
    subp(this.Y, a.Y, b.Y)
    subp(this.U, a.U, b.U)
    subp(this.V, a.V, b.V)
}


color_pyr.prototype.fromRGBA = function(src) {
    var w = src.width, h = src.height;
    for(var y = 0; y < h; y++){
        for(var x = 0; x < w; x++){
            var r = src.data[(y * w + x) * 4],
                g = src.data[(y * w + x) * 4 + 1],
                b = src.data[(y * w + x) * 4 + 2];

            var Y = r *  .299000 + g *  .587000 + b *  .114000,
                U = r * -.168736 + g * -.331264 + b *  .500000 + 128,
                V = r *  .500000 + g * -.418688 + b * -.081312 + 128;

            this.Y.data[0].data[y * w + x] = Y;
            this.U.data[0].data[y * w + x] = U;
            this.V.data[0].data[y * w + x] = V;
        }
    }
}

color_pyr.prototype.mulLevel = function(n, c){
    function mul(chan){
        var d = chan.data[n];
        for(var i = 0; i < d.cols * d.rows; i++){
            d.data[i] *= c;
        }
    }
    mul(this.Y);
    mul(this.U);
    mul(this.V);
}

function immul(n, chan, schan, c){
    var d = chan.data[n],
        e = schan.data[n];

    for(var i = 0; i < d.cols * d.rows; i++){
        d.data[i] = c * d.data[i] + e.data[i];
    }
}

color_pyr.prototype.exportLayer = function(layer, dest) {
    var Yp = this.Y.data[layer].data,
        Up = this.U.data[layer].data,
        Vp = this.V.data[layer].data,
        Dd = dest.data;

    var w = this.Y.data[layer].cols,
        h = this.Y.data[layer].rows;
    
    for(var y = 0; y < h; y++){
        for(var x = 0; x < w; x++){
            var i = y * w + x;
            var Y = Yp[i], U = Up[i], V = Vp[i];
            var r = Y + 1.4075 * (V - 128),
                g = Y - 0.3455 * (U - 128) - (0.7169 * (V - 128)),
                b = Y + 1.7790 * (U - 128);
            
            var n = 4 * (y * dest.width + x);
            
            Dd[n] = r;
            Dd[n + 1] = g;
            Dd[n + 2] = b;
            Dd[n + 3] = 255;          

        }
    }
}

color_pyr.prototype.exportLayerRGB = function(layer, dest) {
    var Yp = this.Y.data[layer].data,
        Up = this.U.data[layer].data,
        Vp = this.V.data[layer].data,
        Dd = dest.data;

    var w = this.Y.data[layer].cols,
        h = this.Y.data[layer].rows;
    
    for(var y = 0; y < h; y++){
        for(var x = 0; x < w; x++){
            var i = y * w + x;
            var Y = Yp[i], U = Up[i], V = Vp[i];
            var n = 4 * (y * dest.width + x);
            Dd[n] = 127 + 10 * Y;
            Dd[n + 1] = 127 + 10 * U;
            Dd[n + 2] = 127 + 10 * V;
            Dd[n + 3] = 255;          

        }
    }
}


color_pyr.prototype.toRGBA = function(dest) {
    for(var i = 0; i < this.levels; i++) this.exportLayerRGB(i, dest);
}





function imadd(a, b){
    var a_d = a.data, b_d = b.data;
    var w = a.cols, h = a.rows, n = w * h;
    for(var i = 0; i < n; ++i){
        a_d[i] = a_d[i] + b_d[i];
    }
}

function imsub(a, b){
    var a_d = a.data, b_d = b.data;
    var w = a.cols, h = a.rows, n = w * h;
    for(var i = 0; i < n; ++i){
        b_d[i] = (b_d[i] - a_d[i]);
    }
}

var first_frame = true;

var alpha = 8
var lambda_c = 16 
var r1 = 0.9
var r2 = 0.05
var chromAttenuation = 0.5;

var exaggeration_factor = 20;
function evm(){
    var imageData = ctx.getImageData(0, 0, vidWidth, vidHeight);
    img_pyr.fromRGBA(imageData)

    img_pyr.pyrDown()
    img_ryp.pyrUp(img_pyr)
    img_pyr.lpyrDown(img_ryp)

    lowpass1.iirFilter(img_pyr, r1);
    lowpass2.iirFilter(img_pyr, r2);
    filtered.setSubtract(lowpass1, lowpass2);

    var delta = lambda_c / 8 / (1+alpha);
    var lambda = Math.sqrt(vidHeight * vidHeight + vidWidth * vidWidth) / 3;

    // for(var n = filtered.levels - 1; n >= 0; n--){
    for(var n = 0; n < filtered.levels; n++) {
        var currAlpha = lambda / delta / 8 - 1;
        currAlpha *= exaggeration_factor;
        if(n <= 0 || n == filtered.levels - 1) {
            filtered.mulLevel(n, 0)
        }else if(currAlpha > alpha){
            filtered.mulLevel(n, alpha)
        }else{
            filtered.mulLevel(n, currAlpha)
        }
        lambda = lambda / 2;
    }

    img_ryp.lpyrUp(filtered)


    var merp = ctx.createImageData(vidWidth, vidHeight)
    // img_ryp.toRGBA(merp)
    img_pyr.fromRGBA(imageData)
    // img_pyr.addLevel(0, img_ryp)
    immul(0, img_ryp.Y, img_pyr.Y, 1)
    immul(0, img_ryp.U, img_pyr.U, chromAttenuation)
    immul(0, img_ryp.V, img_pyr.V, chromAttenuation)

    img_ryp.exportLayer(0, merp)
    ctx.putImageData(merp, 0, 0);


}




function clamp(n) { return Math.max(0, Math.min(255, n))}
