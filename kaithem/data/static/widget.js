toSet = {};
toPoll= {};

function KWidget_register(key,callback)
{
	if (key in toPoll)
	{
		toPoll[key].push(callback);
	}
	else
	{
		toPoll[key] = [callback];
	}
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

if((Object.keys(toSet).length+Object.keys(toPoll).length)>0)
    { 
	poll();
    }
window.setTimeout(pollLoop, 120);

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
		for(var j in toPoll[i])
		{
			toPoll[i][j](resp[i]);
		}
	}
	toSet={};


}

xmlhttp=new XMLHttpRequest();
xmlhttp.open("GET","/widgets/ws_allowed",false);
xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
xmlhttp.send();
xmlDoc=xmlhttp.responseText;
if (xmlDoc == 'True' & false)
{
	function wspollLoop()
	{

	if((Object.keys(toSet).length+Object.keys(toPoll).length)>0)
	    { 
		wpoll();
	    }	
	}

	var connection = new WebSocket("wss://"+window.location.host + '/widgets/ws');

	connection.onmessage = function(e){
	var resp = JSON.parse(e.data);

	for (var i in resp)
		{
			for(var j in toPoll[i])
			{
				toPoll[i][j](resp[i]);
			}
		}
	window.setTimeout(wspollLoop, 80);

	}

	connection.onopen = function(e)
	{
		wspollLoop();
		wspollLoop();
	}

	  
	function wpoll()
	{
		var toSend = {'upd':toSet,'req':Object.keys(toPoll)};
		var j = JSON.stringify(toSend);
		connection.send(j);
		toSet={};
	}
}
else
{
	pollLoop();
}


