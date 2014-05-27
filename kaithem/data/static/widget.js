toSet = {};
toPoll= {};

function KWidget_register(key,callback)
{
	toPoll[key] = callback;
}


function setValue(key,value)
{
	toSet[key]=value;
}

function pollLoop()
{
    var t;
    t = Date.now();
	poll();
	window.setTimeout(pollLoop, 250-Math.max((Date.now()-t),0) );
}

function poll()
{
	var toSend = {'upd':toSet,'req':Object.keys(toPoll)};
	var j = JSON.stringify(toSend);
	xmlhttp=new XMLHttpRequest();
	xmlhttp.open("GET","/widgets?json="+escape(j),false);
    xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
	xmlhttp.send();
	xmlDoc=xmlhttp.responseText;
	resp = JSON.parse(xmlDoc);
	
	for (var i in resp)
	{
		toPoll[i](resp[i]);
	}

}

pollLoop();