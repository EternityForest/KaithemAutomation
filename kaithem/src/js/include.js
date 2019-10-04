// include.js
//
// Copyright 2016, Morgan McGuire
// http://casual-effects.com
//
// Distributed under the MIT License
// https://opensource.org/licenses/MIT

console.log("include.js loaded by " + location.href);

// Avoid repeatedly loading the script
if (! window.include) {
    window.include = 1;

    addEventListener('load', function() {
        var doc = document;

        // Helper function for use by children
        function sendContentsToMyParent() {
            var head = doc.head;
            var body = doc.body;

            console.log(location.href + " sent message to parent");
            if (parentBase !== myBase) {
                makeURLsAbsolute(head);
                makeURLsAbsolute(body);
            }
            parent.postMessage(myID + '=' + head.innerHTML + body.innerHTML, '*');
        }
        
        function makeOneURLAbsolute(url) {
            // If the url is already absolute (or null), return it. Otherwise, prepend my base URL
            return url && (/^#|^[A-Za-z]+:\/\/|^\//.test(url) ? url : myBase + url);
        }
        
        // Fix all relative URLs to absolute in element and all of its children recursively
        function makeURLsAbsolute(element) {
            element.src = makeOneURLAbsolute(element.src);
            element.href = makeOneURLAbsolute(element.href);

            var c = element.children;
            for (var i = 0; i < c.length; ++i) {
                makeURLsAbsolute(c[i]);
            }
        }
        
        // Strip the filename from the url, if there is one (and it is a string)
        function removeFilename(url) {
            return url && url.substr(0, url.lastIndexOf('/') + 1);
        }
        
        // Parse my own URL (if I am a child)
        var tmp = /([^?]+)(?:\?id=(inc\d+)&p=([^&]+))?/.exec(location.href);
        var myBase = removeFilename(tmp[1]);
        var myID = tmp[2];
        var parentBase = removeFilename(tmp[3] && decodeURIComponent(tmp[3]));
        
        // Convert the includeTags to an array before we begin to modify the document.
        // Otherwise they will no longer be valid.
        var includeTags = [].slice.call(doc.getElementsByTagName('include'));
        
        var numChildrenLeft = includeTags.length; // This will be used as a counter below

        var IAmAChild = myID; // !== null
        var IAmAParent = numChildrenLeft;
        
        var childFrameStyle = 'display:none';
        
        if (IAmAParent) {
            // Prepare to receive messages from the embedded children
            addEventListener("message", function (event) {
                // Parse the message. Ensure that it is for the include.js system.
                var childID = false;
                var childBody = event.data.replace(/^(inc\d+)=/, function (match, a) {
                    childID = a;
                    return '';
                });
                
                if (childID) {
                    // This message was for the include.js system
                    console.log(location.href + ' received a message from child ' + childID);
                    
                    // Replace the corresponding node's contents
                    var childFrame = doc.getElementById(childID);
                    childFrame.outerHTML = childBody;
                    
                    if (IAmAChild && (--numChildrenLeft === 0)) {
                        sendContentsToMyParent();
                    }
                }
            });
            
            var counter = 0;
            includeTags.forEach(function (element) {
                // Replace this tag with a frame that loads the document.  Once loaded, it will
                // send a message with its contents for use as a replacement.
                var src = element.attributes['src'].nodeValue;
                var childID = 'inc' + (++counter);
                element.outerHTML = '<iframe src="' + src + '?id=' + childID + '&p=' + encodeURIComponent(myBase) + 
                    '"id="' + childID + '"style="' + childFrameStyle + '"></iframe>';
            });
        } else if (IAmAChild) {
            sendContentsToMyParent();
        }
    });
}