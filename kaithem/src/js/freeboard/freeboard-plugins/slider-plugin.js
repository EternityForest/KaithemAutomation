// ┌────────────────────────────────────────────────────────────────────┐ \\
// │ freeboard-slider-plugin                                            │ \\
// ├────────────────────────────────────────────────────────────────────┤ \\
// │ http://blog.onlinux.fr/                                            │ \\
// ├────────────────────────────────────────────────────────────────────┤ \\
// │ Licensed under the MIT license.                                    │ \\
// ├────────────────────────────────────────────────────────────────────┤ \\
// │ Freeboard widget plugin.                                           │ \\
// └────────────────────────────────────────────────────────────────────┘ \\
(function () {
	//
	// DECLARATIONS
	//
	var LOADING_INDICATOR_DELAY = 1000;
	var SLIDER_ID = 0;

	freeboard.addStyle('.slider', "border: 2px solid #3d3d3d;background-color: #222;margin: 10px;");
	freeboard.addStyle('.slider-label', 'margin-left: 10px; margin-top: 10px; text-transform: capitalize;');
	freeboard.addStyle('.myui-slider-handle', "width: 1.5em !important; height: 1.5em !important; border-radius: 50%; top: -.4em !important; margin-left:-1.0em !important;");
	freeboard.addStyle('.ui-slider-range', 'background: #F90;');

	// ## A Widget Plugin
	//
	// -------------------
	// ### Widget Definition
	//
	// -------------------
	// **freeboard.loadWidgetPlugin(definition)** tells freeboard that we are giving it a widget plugin. It expects an object with the following:
	freeboard.loadWidgetPlugin({
		// Same stuff here as with datasource plugin.
		"type_name": "slider_plugin",
		"display_name": "Slider",
		"description": "Interactive Slider Plugin with 2-way data binding",
		// **external_scripts** : Any external scripts that should be loaded before the plugin instance is created.

		// **fill_size** : If this is set to true, the widget will fill be allowed to fill the entire space given it, otherwise it will contain an automatic padding of around 10 pixels around it.
		"fill_size": true,
		"settings": [
			{
				"name": "title",
				"display_name": "Title",
				"type": "text"
			},

			{
				"name": "unit",
				"display_name": "Unit of measure",
				"type": "text"
			},

			{
				"name": "min",
				"display_name": "Min",
				"type": "calculated",
				"default_value": "0"
			},
			{
				"name": "max",
				"display_name": "Max",
				"type": "calculated",
				"default_value": "100"
			},
			{
				"name": "step",
				"display_name": "Step",
				"type": "calculated",
				"default_value": "1"
			},
			{
				"name": "mode",
				"display_name": "Mode",
				"type": "option",
				"options": [
					{
						"name": "Real Time",
						"value": "input"
					},
					{
						"name": "When Released",
						"value": "change"
					}
				]
			},
			{
				"name": "value",
				"display_name": "Value",
				"type": "calculated"
			},
			{
				name: "target",
				display_name: "Data target when value changed",
				type: "target"
			}
		],
		// Same as with datasource plugin, but there is no updateCallback parameter in this case.
		newInstance: function (settings, newInstanceCallback) {
			newInstanceCallback(new slider(settings));
		}
	});


	// ### Widget Implementation
	//
	// -------------------
	// Here we implement the actual widget plugin. We pass in the settings;
	var slider = function (settings) {
		var self = this;
		currentSettings = settings;
		currentSettings.unit = currentSettings.unit || ''

		var thisWidgetId = "slider-" + SLIDER_ID++;
		var thisWidgetContainer = $('<div class="slider-widget slider-label" id="__' + thisWidgetId + '"></div>');


		var titleElement = $('<h2 class="section-title slider-label"></h2>');
		var valueElement = $('<div id="value-' + thisWidgetId + '" style="display:inline-block; padding-left: 10px; font-weight:bold; color: #d3d4d4" ></div>');
		var sliderElement = $('<input/>', { type: 'range', id: thisWidgetId });
		var theSlider = '#' + thisWidgetId;
		var theValue = '#' + "value-" + thisWidgetId;

		//console.log( "theSlider ", theSlider);

		var value = (_.isUndefined(currentSettings.value) ? 50 : currentSettings.value);
		titleElement.html((_.isUndefined(currentSettings.title) ? "" : currentSettings.title));
		self.min = (_.isUndefined(currentSettings.min) ? 0 : currentSettings.min);
		self.max = (_.isUndefined(currentSettings.max) ? 100 : currentSettings.max);
		self.step = (_.isUndefined(currentSettings.step) ? 100 : currentSettings.step);

		self.value = currentSettings.value || 0;

		var requestChange = false;
		var target;

		// Here we create an element to hold the text we're going to display. We're going to set the value displayed in it below.

		// **render(containerElement)** (required) : A public function we must implement that will be called when freeboard wants us to render the contents of our widget. The container element is the DIV that will surround the widget.
		self.render = function (containerElement) {
			$(containerElement)
				.append(thisWidgetContainer);
			titleElement.appendTo(thisWidgetContainer);
			$(titleElement).append(valueElement);
			sliderElement.appendTo(thisWidgetContainer);

			$(theSlider).attr('min', self.min);
			$(theSlider).attr('max', self.max);
			$(theSlider).attr('step', self.step);

			$(theSlider).on('input', function (e) { $("#value-" + thisWidgetId).html(e.value) });


			$(theValue).html(self.value + currentSettings.unit);

			$(theSlider).on('change',
				function (e) {
					if (_.isUndefined(currentSettings.target)) { }
					else {
						//Avoid loops, only real user input triggers this
						if (true) {
							self.dataTargets.target(e.target.value);
						}
					}
				});
			$(theSlider).on('input',
				function (e) {
					self.value = e.target.value;
					$(theValue).html(e.target.value + currentSettings.unit);

					if (currentSettings.mode == 'change') {
						//This mode does not affect anything till the user releases the mouse
						return;
					}
					if (_.isUndefined(currentSettings.target)) { }
					else {
						//todo Avoid loops, only real user input triggers this
						if (true) {
							self.dataTargets.target(e.target.value);
						}
					}
				}
			);
			$(theSlider).removeClass("ui-widget-content");
		}

		// **getHeight()** (required) : A public function we must implement that will be called when freeboard wants to know how big we expect to be when we render, and returns a height. This function will be called any time a user updates their settings (including the first time they create the widget).
		//
		// Note here that the height is not in pixels, but in blocks. A block in freeboard is currently defined as a rectangle that is fixed at 300 pixels wide and around 45 pixels multiplied by the value you return here.
		//
		// Blocks of different sizes may be supported in the future.
		self.getHeight = function () {
			if (currentSettings.size == "big") {
				return 2;
			}
			else {
				return 1;
			}
		}

		// **onSettingsChanged(newSettings)** (required) : A public function we must implement that will be called when a user makes a change to the settings.
		self.onSettingsChanged = function (newSettings) {
			// Normally we'd update our text element with the value we defined in the user settings above (the_text), but there is a special case for settings that are of type **"calculated"** -- see below.
			currentSettings = newSettings;
			titleElement.html((_.isUndefined(newSettings.title) ? "" : newSettings.title));
			$(titleElement).append(valueElement);
			currentSettings.unit = currentSettings.unit || ''

			$(theValue).html(self.value + currentSettings.unit);

		}

		// **onCalculatedValueChanged(settingName, newValue)** (required) : A public function we must implement that will be called when a calculated value changes. Since calculated values can change at any time (like when a datasource is updated) we handle them in a special callback function here.
		self.onCalculatedValueChanged = function (settingName, newValue) {

			// Remember we defined "the_text" up above in our settings.
			if (settingName == "value") {
				self.value = newValue

				$(valueElement).html(newValue + currentSettings.unit);

				//Attempt to break l00ps
				if(newValue!=$(theSlider).val())
				{
					$(theSlider).val(newValue);
				}
			}
			if(settingName=='step')
			{
				self.step=newValue
				$(theSlider).attr('step', self.step);
			}
			if (settingName == "max") {
				if (newValue > self.min) {
					self.max = newValue;
					$(theSlider).attr('max', newValue);
				} else {
					currentSettings.max = self.max; // Keep it unchanged
					freeboard.showDialog($("<div align='center'> Max value cannot be lower than Min value!</div>"), "Warning!", "OK", null, function () { });
				}
			}
			if (settingName == "min") {
				if (newValue <self. max) {
					self.min = newValue;
					$(theSlider).attr('min', newValue);
				} else {
					currentSettings.min = self.min;// Keep it unchanged
					freeboard.showDialog($("<div align='center'> Min value cannot be greater than Max value!</div>"), "Warning!", "OK", null, function () { });
				}
			}
		}


		// **onDispose()** (required) : Same as with datasource plugins.
		self.onDispose = function () {
		}
	}
}());
