---
allow-origins: ['*']
allow-xss: false
auto-reload: false
auto-reload-interval: 5.0
dont-show-in-index: false
mimetype: text/html
no-header: false
no-navheader: false
require-method: [GET, POST]
require-permissions: []
resource-timestamp: 1572490979259984
resource-type: page
template-engine: markdown

---
Pages
-----

Pages let you embed small amounts of HTML directly in a scene. They are rendered as a vue template.


Any variable in the scene that begins with "pagevars." will be shared with the page, and can be accessed by the same name.
List and object variables are not shared.

To set a variable, you call `setVar(key, value)`.  Unlike when reading variables, you do not need to prefix with pagevars.

`setVar("foo", 8)` sets `pagevars.foo` to 8

You may call the function `sendEvent("page.evtname",9)` to send an event, value pair to the scene, so long as the name begins with page.
Events are processed by cue logic like any other.

 
Pages are an Advanced Feature requiring `/admin/modules.edit`. You cannot modify a scene page, delete a scene with one, or upload one without that permission.

Viewing a page only requires `users.chandler.pageview`.


Here is an example page:

```html
<div style="display:flex; flex-direction:column; width:100%; height:100%; align-items: center; justify-content:center; font-size:400%">
    <div>
        Centered Content:
    </div>
    
    <div>
        {{pagevars.foo}}
    </div>
</div>
```