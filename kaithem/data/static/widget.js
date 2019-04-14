KWidget_toSend = [];
KWidget_polled = [];
var justSet ={};

KWidget_serverMsgCallbacks= {
	"__WIDGETERROR__":[
		function(m)
		{
			console.error(m);
		}

	]
};


KWidget_subscriptions = []
KWidget_connection = 0


function KWidget_subscribe(key,callback)
{


	if (key in KWidget_serverMsgCallbacks)
	{
		KWidget_serverMsgCallbacks[key].push(callback);
	}

	else
	{
		KWidget_serverMsgCallbacks[key] = [callback];
	}

    //If the ws is open, send the subs list, else wait for the connection handler to do it.
	if(KWidget_connection)
	{
		if( KWidget_connection.readyState==1)
		{
			var j = {"subsc":Object.keys(KWidget_serverMsgCallbacks),"req":[],"upd":[]}
			KWidget_connection.send(JSON.stringify(j))
	    }
    }
}

function KWidget_register(key, callback)
{
    KWidget_polled.push(key);
	KWidget_subscribe(key,callback);
}
function KWidget_setValue(key,value)
{
	KWidget_toSend.push([key,value])
	KWidget_poll_ratelimited();
}

function KWidget_sendValue(key,value)
{
	KWidget_toSend.push([key,value])
	KWidget_poll_ratelimited();
}

function pollLoop()
{

if((Object.keys(KWidget_toSend).length+Object.keys(KWidget_serverMsgCallbacks).length)>0)
    {
	poll();
    }
window.setTimeout(pollLoop, 120);

}

KWidget_can_show_error = 1;
KWidget_usual_delay = 0

function poll()
{
	var toSend = {'upd':KWidget_toSend,'req':[]};
	var j = JSON.stringify(toSend);
	xmlhttp=new XMLHttpRequest();
	xmlhttp.open("GET","/widgets?json="+escape(j),false);
    xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
	xmlhttp.send();
	KWidget_dirty = {};
	xmlDoc=xmlhttp.responseText;
	try
	{
	resp = JSON.parse(xmlDoc);
	KWidget_usual_delay = 0;
    }
	catch(err)
	{
        KWidget_usual_delay = 250;
	}
			for(var j in KWidget_serverMsgCallbacks[i])
			{
				KWidget_serverMsgCallbacks[i][j](resp[i]);
			}

	justSet = KWidget_toSend;
	KWidget_toSend={};

}
KWidget_reconnect_timeout = 1500;

KWidget_connect = function()
{
	if (true)
	{

		KWidget_connection = new WebSocket(window.location.protocol.replace("http","ws")+"//"+window.location.host + '/widgets/ws');

		KWidget_connection.onclose = function(e){
			console.log(e);
			setTimeout( KWidget_connect , KWidget_reconnect_timeout);
		};

		KWidget_connection.onerror = function(e){
			console.log(e);

			if (KWidget_connection,readyState != 1)
			{
				KWidget_reconnect_timeout = Math.min(KWidget_reconnect_timeout*2, 20000);
				setTimeout( KWidget_connect , KWidget_reconnect_timeout);
	    }
		};


		KWidget_connection.onmessage = function(e){
			try{
		        var resp = JSON.parse(e.data);
			}
			catch(err)
			{
				console.log("JSON Parse Error in websocket response:\n"+e.data);
			}

        //Iterate messages
		for (var n=0;n<resp.length; n++)
			{
				i=resp[n]
				for(j in KWidget_serverMsgCallbacks[i[0]])
					{
						KWidget_serverMsgCallbacks[i[0]][j](resp[n][1]);
					}
			}
		}

		KWidget_connection.onopen = function(e)
		{
			var j = JSON.stringify({"subsc":Object.keys(KWidget_serverMsgCallbacks),"req":[],"upd":{}})
			KWidget_connection.send(j)
			console.log("WS Connection Initialized");
			KWidget_reconnect_timeout = 1500;
			window.setTimeout(KWidget_wpoll, 250);
		}

		KWidget_wpoll = function()
		{
			if(KWidget_toSend.length>0 || KWidget_polled.length>0)
			{
				var toSend = {'upd':KWidget_toSend,'req':Object.keys(KWidget_polled)};
				var j = JSON.stringify(toSend);
				KWidget_connection.send(j);
				justSet = KWidget_toSend;
				KWidget_toSend=[];
			}

			if(KWidget_toSend.length>0 || KWidget_polled.length>0)
			{
			    window.setTimeout(KWidget_poll_ratelimited, 120);
		    }

			KWidget_pollWaiting =false
		}

		KWidget_lastSend =0
		KWidget_pollWaiting =false

        //Check if wpoll has ran in the last 44ms. If not run it.
	    //If it has, set a timeout to check again.
	    //This code is only possible because of the JS single threadedness.
	    KWidget_poll_ratelimited = function()
		{
			var d = new Date();
			var n = d.getTime();

			if(n-KWidget_lastSend>44)
			{
				KWidget_lastSend = n;
				KWidget_wpoll()
			}
			//If we are already waiting on a poll, don't re-poll.
			else{
				if(KWidget_pollWaiting)
				{
					return
				}
				KWidget_pollWaiting = true;
				window.setTimeout(KWidget_poll_ratelimited,50-(n-KWidget_lastSend))
			}
		}

	}
	else
	{
		pollLoop();
	}
};

KWidget_connect();
