// # Building a Freeboard Plugin
//
// A freeboard plugin is simply a javascript file that is loaded into a web page after the main freeboard.js file is loaded.
//
// Let's get started with an example of a datasource plugin and a widget plugin.
//
// -------------------

// Best to encapsulate your plugin in a closure, although not required.
(function()
{
	// ## A Datasource Plugin
	//
	// -------------------
	// ### Datasource Definition
	//
	// -------------------
	// **freeboard.loadDatasourcePlugin(definition)** tells freeboard that we are giving it a datasource plugin. It expects an object with the following:
	freeboard.loadDatasourcePlugin({
		// **type_name** (required) : A unique name for this plugin. This name should be as unique as possible to avoid collisions with other plugins, and should follow naming conventions for javascript variable and function declarations.
		"type_name"   : "kaithem_api_plugin",
		// **display_name** : The pretty name that will be used for display purposes for this plugin. If the name is not defined, type_name will be used instead.
		"display_name": "Kaithem Widget API",
        // **description** : A description of the plugin. This description will be displayed when the plugin is selected or within search results (in the future). The description may contain HTML if needed.
        "description" : "Read or write data to or from kaithem.widgets.DataSource widgets.  The data key will always be the same as the widget ID.   Tag points use tag:tagname.  tag.control:tagname is a write only interface. Write null to release.",
		// **external_scripts** : Any external scripts that should be loaded before the plugin instance is created.
	
		// **settings** : An array of settings that will be displayed for this plugin when the user adds it.
		"settings"    : [
                {
                    // **name** (required) : The name of the setting. This value will be used in your code to retrieve the value specified by the user. This should follow naming conventions for javascript variable and function declarations.
                    "name"         : "apis",
                    // **display_name** : The pretty name that will be shown to the user when they adjust this setting.
                    "display_name" : "APIs to use",
					// **type** (required) : The type of input expected for this setting. "text" will display a single text box input. Examples of other types will follow in this documentation.
	
					"type"        : "array",
	
					"settings"    : [
						{
							"name"        : "name",
							"display_name": "Widget ID",
							"type"        : "text",
							"options": function(){return KaithemDataSourcesListing}
						}
					],
                    // **default_value** : A default value for this setting.
                    "default_value": "",
                    // **description** : Text that will be displayed below the setting to give the user any extra information.
                    "description"  : "All the widget IDs that you want to access.   You must configure them here to use them.",
                    // **required** : If set to true, the field will be required to be filled in by the user. Defaults to false if not specified.
                    "required" : true
                }
		],
		// **newInstance(settings, newInstanceCallback, updateCallback)** (required) : A function that will be called when a new instance of this plugin is requested.
		// * **settings** : A javascript object with the initial settings set by the user. The names of the properties in the object will correspond to the setting names defined above.
		// * **newInstanceCallback** : A callback function that you'll call when the new instance of the plugin is ready. This function expects a single argument, which is the new instance of your plugin object.
		// * **updateCallback** : A callback function that you'll call if and when your datasource has an update for freeboard to recalculate. This function expects a single parameter which is a javascript object with the new, updated data. You should hold on to this reference and call it when needed.
		newInstance   : function(settings, newInstanceCallback, updateCallback)
		{
			// myDatasourcePlugin is defined below.
			newInstanceCallback(new myDatasourcePlugin(settings, updateCallback));
		}
	});


	// ### Datasource Implementation
	//
	// -------------------
	// Here we implement the actual datasource plugin. We pass in the settings and updateCallback.
	var myDatasourcePlugin = function(settings, updateCallback)
	{
		// Always a good idea...
		var self = this;

		// Good idea to create a variable to hold on to our settings, because they might change in the future. See below.
		var currentSettings = settings;
		self.updateCallback=updateCallback

		self.oldApis = {}

        self.handler={
			set: function(obj,prop,val)
			{
				if (_.isUndefined(val))
				{
					throw new Error("Can't use undefined val here")
				}

				//This might not even be a value that exists, and if it is we don't want to clobber it before we have even read it.
				if (_.isUndefined(obj[prop]))
				{
					throw new Error("Nonexistent tag API, or connection not established yet")
				}
					
				kaithemapi.sendValue(prop, val);

				if(obj[prop]==val)
				{
					return;
				}
				obj[prop]=val;

				updateCallback(self.proxy);

			}

        }
		self.data={}
        self.proxy = new Proxy(self.data, self.handler)
        

		/* This is some function where I'll get my data from somewhere */
		function getData()
		{
			var newData= self.proxy ; // Just putting some sample data in for fun.

			/* Get my data from somewhere and populate newData with it... Probably a JSON API or something. */
			/* ... */

			// I'm calling updateCallback to tell it I've got new data for it to munch on.
			updateCallback(newData);
		}


        self.dataHandlers ={}
        
        self.subscribe=function(t){
            var f = function(data)
            {
                self.data[t]=data;
                self.updateCallback(self.proxy);
            }
            kaithemapi.subscribe(t,f)
            self.dataHandlers[t]=f
        }
        
        self.unsubscribe=function(t){
            kaithemapi.unsubscribe(t,self.dataHandlers[t])
            delete self.dataHandlers[t]
        }
        
        
		// **onSettingsChanged(newSettings)** (required) : A public function we must implement that will be called when a user makes a change to the settings.
		self.onSettingsChanged = function(newSettings)
		{
			var x = []

            for(i of newSettings['apis'])
            {
                if (! (i in self.oldApis))
                {
                    self.subscribe(i.name);
					self.oldApis[i.name]=1
					x.push(i.name)
                }
            }
            
            for(i in self.oldApis)
            {
                if (x.indexOf(i)==-1)
                {
                    self.unsubscribe(i);
					delete self.oldApis[i]

                }
            }
            
			// Here we update our current settings with the variable that is passed in.
			currentSettings = newSettings;
			self.oldSettings= newSettings;


            updateCallback(self.proxy)
		}

		self.onSettingsChanged(settings);

		// **updateNow()** (required) : A public function we must implement that will be called when the user wants to manually refresh the datasource
		self.updateNow = function()
		{
			// Most likely I'll just call getData() here.
			getData();
		}

		// **onDispose()** (required) : A public function we must implement that will be called when this instance of this plugin is no longer needed. Do anything you need to cleanup after yourself here.
		self.onDispose = function()
		{
		
		}

	}

}());
