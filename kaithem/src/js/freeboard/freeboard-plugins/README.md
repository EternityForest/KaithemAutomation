# freeboard-plugins
<h1>This is a collection of widget plugins for freeboard.io</h1>
<h4><ul>
<li>Actuator widget plugin</li>
<li>Switch widget plugin</li>
<li>Slider widget plugin</li>
<li>Dynamic highcharts widget plugin</li>
</ul>
</h4>
<a href="/freeboard-widget-plugins.png"><img class="wp-image-461 size-full" src="/freeboard-widget-plugins.png" alt=" Widget plugins" /></a>

<h2>Actuator widget plugin</h2>

<a href="/actuator-3.png"><img class="wp-image-461 size-full" src="/actuator-3.png" alt="Actuator Widget" width="346" height="426" /></a>

This widget plugin is based on the interactive-indicator created by <a href="https://github.com/stufisher/plugins" target="_blank">Stufisher</a>.
<h2>See it in action @ <a href="https://goo.gl/hbAXXU" target="_blank">https://goo.gl/hbAXXU</a></h2>
I modified it  mainly to fit my needs. It merely links the states ON or OFF to web URL.

<a href="/actuator-2.png"><img class="alignleft size-full wp-image-460" src="/actuator-2.png" alt="actuator-2" width="965" height="850" /></a>A click on the indicator switches the state ON/OFF of the actuator which is bound to a http request.

&nbsp;

&nbsp;

&nbsp;
<h1>INSTALLATION</h1>
<p style="color: #333333;">For installation of any plugins of the collection, proceed as the same as the installation of the actuator.js widget plugin.</p>
<p style="color: #333333;">Copy the plugin (actuator.js  from github onlinux/freeboard-actuator-plugin) to your freeboard installation, for example:</p>

<pre style="color: #333333;"><code>$ cp ./actuator.js /freeboard/plugins/
</code></pre>
<p style="color: #333333;">edit the <a style="color: #4078c0;" href="https://github.com/Freeboard/freeboard/blob/master/index.html#L14">freeboard index.html file</a> and add a link to the plugin near the end of the head.js script loader, like:</p>

<pre style="color: #333333;"><code>head.js(
  'js/freeboard_plugins.min.js',
  'plugins/actuator.js',
  $(function() {
    //DOM Ready
    freeboard.initialize(true);
  })</code></pre>
<a href="/actuator-1.png"><img class="alignleft size-full wp-image-459" src="/actuator-1.png" alt="actuator-1" width="965" height="850" /></a>
