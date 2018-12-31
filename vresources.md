&lt;%include file="/pageheader.html"/&gt;

Kaithem Help

Virtual Resources
=================

<a href="" id="intro"></a>Introduction
--------------------------------------

A Virtual Resource is an object that can exist in a module along with events, pages, etc, but is created at runtime through code and is never saved to disk. VirtualResources all descend from the class kaithem.resource.VirtualResource

Virtual resources support a few handy features. They have an \_\_html\_repr\_\_ method which returns a short piece of HTML to show in the module listing, and they support the concept of replacements and handoffs for seamless code updates.

Every VirtualResource has a .name attribute which is either None, or is set the first time the resource is inserted. You do this by saying module\['foo'\] = vr from within any page or event. The name will become a tuple of (module, resource).

If you try to overwrite an existing physical resource in this way, a RuntimeError results. If you try to overwrite another virtual resource, it will succeed, but only if the new one is of the same class or a subclass of the original.

VirtualResources dissapear as soon as there are no references to them.

Every VirtualResource also has an interface() method, which for the most part returns a fully transparent proxy to the VirtualResource

However, when a VirtualResource is overwritten in a module namespace, any interfaces pointing to the old resource get updated to point to the new one. To best take advantage of this, avoid passing direct refernences to a VirtualResource, and pass around the interfaces, or directly look them up.

Once an object has been replaced, it should no longer be used, but must proxy any important calls, and calls that would affect the mutable state of the object through to the new one.

Objects are replaced using the old\_one.handoff(new\_one) method, which also sets old\_one.replacement, which is normally None, to the new one. If the object has already been replaced, it passes through the call to the replacement.

Should you extend handoff(), you must do this same check, as in

    x = self.replacement
    if x and (not x is other):
        return x.handoff(self)

By subclassing VirtualResource and extending handoff(), you can create objects that allow seamless code modification at runtime without noticable interruptions. However, there may still be sneaky transient references to the old one around. One example is if the replacement happens just after a method call to the old one, before it has a chance to complete. Another example is if you have a reference to a property of the old object, as the proxying is not recursive.

Another issue that can occur with VirtualResources is that if other code can add things to them, such as callbacks, those will all dissapear when the object gets replaced unless you copy them over in your handoff()

In general, mutable runtime data should be copied over(Including open sockets, game score data, lighting values, etc), wheras mostly-static configuration and code should not be.

Be sure to clearly document what does and does not get transferred.

Aside from handoff, replacement, name, and interface, VirtualResource does not define any public names and doesn't do much when instantiated, so you can use them just like any other object for the most part.

&lt;%include file="/pagefooter.html"/&gt;
