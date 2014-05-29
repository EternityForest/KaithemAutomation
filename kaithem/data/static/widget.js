toSet = {};
toPoll= {};

function KWidget_register(key,callback)
{
	toPoll[key] = callback;
}


function KWidget_setValue(key,value)
{
	toSet[key]=value;
}

function KWidget_sendValue(key,value)
{
	if(key in toSet)
	{
		toSet[key].push(value);
	}
	else
	{
		toSet[key]=[value];
	}
}

function pollLoop()
{
    var t;
    t = Date.now();
	poll();
	window.setTimeout(pollLoop, 100-Math.max((Date.now()-t),0) );
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
	toSet={};

}

pollLoop();