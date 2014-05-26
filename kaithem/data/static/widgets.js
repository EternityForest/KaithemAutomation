toSet = {}
toPoll= {}

function KWidget_register(key,callback)
{
	[key] = callback;
}


function setValue(key,value)
{
	toSet[key]=value;
}

function pollLoop()
{
	poll();
	window.setTimeout(pollLoop, 350)
}

function poll()
{
	toSend = {'upd':toSet,'req':toPoll}
	xmlhttp=new XMLHttpRequest();
	xmlhttp.open("POST","/ajax/widgets",false);
	xmlhttp.send(toSend);
	xmlDoc=xmlhttp.responsetext;
	resp = JSON.parse(xmlDoc);

	for (var i in resp)
	{
		toPoll[i](resp[i]);
	}
 
}