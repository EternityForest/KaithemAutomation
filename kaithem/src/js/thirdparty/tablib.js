var makeFunction = function(e,a,b,d)
    {
    return function()
    {
        for(i in a)
            {
            a[i][1].style = "display:none";
            e.style = "display:block;"
            }
        var i = d.firstChild;
        while (i)
            {

               i.className ="";
               i =i.nextSibling;
            }
        b.className = "selected-tab";
    }
}

var f =function (n)
    {
                var tabview = n;
                var l = []
                var node = n.firstChild;
                while(node)
                    {
                        if(node.nodeName=="TAB-PANE")
                        {
                            node.style = "display:none";
                            l.push([node.getAttribute("name"), node ]);
                        }
                        node = node.nextSibling;
                    }

                var d = document.createElement("div");
                var buttons = []
                for (i in l)
                    {
                        var b = document.createElement("span");
                        var t = document.createTextNode(l[i][0]);
                        buttons.push(b);
                        b.onclick = makeFunction(l[i][1], l,b,d)
                        b.appendChild(t);
                        d.appendChild(b);
                    }
               tabview.insertBefore(d,tabview.firstChild);
    }
var g = function()
{
var x = document.getElementsByTagName("tab-panel");

for (i in x)
    {
        f(x[i]);
    }
}

window.addEventListener("load", g, false);
