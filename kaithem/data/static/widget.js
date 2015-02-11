toSet = {};
justSet ={};
KWidget_toPoll= {};

function KWidget_register(key,callback)
{
	if (key in KWidget_toPoll)
	{
		KWidget_toPoll[key].push(callback);
	}
	else
	{
		KWidget_toPoll[key] = [callback];
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

if((Object.keys(toSet).length+Object.keys(KWidget_toPoll).length)>0)
    { 
	poll();
    }
window.setTimeout(pollLoop, 120);

}



function poll()
{
	var toSend = {'upd':toSet,'req':Object.keys(KWidget_toPoll)};
	var j = JSON.stringify(toSend);
	xmlhttp=new XMLHttpRequest();
	xmlhttp.open("GET","/widgets?json="+escape(j),false);
    xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
	xmlhttp.send();
	KWidget_dirty = {};
	xmlDoc=xmlhttp.responseText;
	resp = JSON.parse(xmlDoc);
			for(var j in KWidget_toPoll[i])
			{
				KWidget_toPoll[i][j](resp[i]);
			}

	justSet = toSet;
	toSet={};


}

xmlhttp=new XMLHttpRequest();
xmlhttp.open("GET","/widgets/ws_allowed",false);
xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
xmlhttp.send();
xmlDoc=xmlhttp.responseText;
if (xmlDoc == 'True')
{
	function wspollLoop()
	{

	if((Object.keys(toSet).length+Object.keys(KWidget_toPoll).length)>0)
	    { 
		wpoll();
	    }	
	}

	var KWidget_connection = new WebSocket(window.location.protocol.replace("http","ws")+"//"+window.location.host + '/widgets/ws');

	KWidget_connection.onmessage = function(e){
		try{
	var resp = JSON.parse(e.data);
		}
		catch(err)
		{
			console.log("JSON Parse Error in websocket response:\n"+e.data)
		}

	for (var i in resp)
		{
			if((! (i in toSet))&(! (i in toSet)))
			{
				for(var j in KWidget_toPoll[i])
				{
					KWidget_toPoll[i][j](resp[i]);
				}
			}
		}
	window.setTimeout(wspollLoop, 60);

	}

	KWidget_connection.onopen = function(e)
	{
		wspollLoop();
		wspollLoop();
	}

	  
	function wpoll()
	{
		var toSend = {'upd':toSet,'req':Object.keys(KWidget_toPoll)};
		var j = JSON.stringify(toSend);
		KWidget_connection.send(j);
		justSet = toSet;
		toSet={};
	}
}
else
{
	pollLoop();
}


