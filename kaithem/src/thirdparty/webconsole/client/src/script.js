
function openTerminal() {
    var client = new WsptyClient();
    var term = new Terminal();
    var container = document.getElementById('term-container');
    term.open(container);
    
    
    
    function debounce(fn) {
        // throttle to 4 calls per second,
        // call 3 more times after last debounced call 
        // because zoom seems to be asynchronous in chrome,
        // and character measurement returns wrong values for
        // a short time
        var tid = null, counter = 0;
        return function() {
            counter = 3;
            if (tid === null) {
              tid = setInterval(function() {
                  if (--counter < 1) {
                      clearTimeout(tid);
                      tid = null;
                  }
                  fn();
              }, 250);
            }
        };
    }
    
    function measureChar(subjectRow) {
        var contentBuffer = subjectRow.innerHTML;
        subjectRow.style.display = 'inline';
        subjectRow.innerHTML = 'W'; // Common character for measuring width, although on monospace
        var characterWidth = subjectRow.getBoundingClientRect().width;
        subjectRow.style.display = ''; // Revert style before calculating height, since they differ.
        var characterHeight = parseInt(subjectRow.offsetHeight);
        subjectRow.innerHTML = contentBuffer;
        return { width: characterWidth, height: characterHeight };
    }
    
    
    function fitTerminal() {
        var subjectRow = term.rowContainer.firstElementChild;
        var charSize = measureChar(subjectRow);
        // 10px padding
        var ww = window.innerWidth - 10, wh = window.innerHeight - 10;
        container.style.width = ww + 'px';
        container.style.height = wh + 'px';
        // 17px scrollbar
        var cols = Math.floor((ww - 17) / charSize.width);
        var rows = Math.floor(wh / charSize.height);
        term.resize(cols, rows);
    }

    var debouncedFitTerminal = debounce(function() { 
        fitTerminal();
    });
    window.addEventListener('resize', function() {
      setTimeout(debouncedFitTerminal, 1000);
      debouncedFitTerminal();
    });
    fitTerminal();
    
    term.on('data', function(data) {
        client.send(data);
    });
    term.on('resize', function(geom) {
        client.resize(geom.cols, geom.rows);
    });
    term.write('Connecting...\r\n');
    
    var wsProtocol = location.protocol === 'http:' ? 'ws' : 'wss';
    var endpoint = wsProtocol + '://' + location.host + '/wssh' + location.search;
    client.connect({
        ws: new WebSocket(endpoint),
        onError: function(error) {
            term.writeln('Error: ' + error);
        },
        onConnect: function() {
            // Erase our connecting message
            // term.write('\x1b[2K\r');
            client.resize(term.cols, term.rows);
        },
        onClose: function() {
            term.write('\r\nConnection closed by peer');
        },
        onData: function(data) {
            term.write(data);
        }
    });
}

window.addEventListener('load', function() {
  openTerminal();
});
