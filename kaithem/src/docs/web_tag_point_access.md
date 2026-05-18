# Tag Point Access API

Web frontend API for subscribing to and accessing tag point values in Kaithem.

## TagSubscriptionManager

A class for managing tag point subscriptions with local name-based deduplication.

```javascript
import { TagSubscriptionManager } from "/static/js/widget.mjs";

const mgr = new TagSubscriptionManager();
```

### Methods

#### `setSubscription(name, tagname, callback, callWithInitialState)`

Subscribe to a tag point.

- `name` (string): Local identifier for this subscription. Used to track and overwrite previous subscriptions with the same name.
- `tagname` (string): Tag point name (e.g., `/my/tag`). Prefix with `tag:` if needed.
- `callback` (function): Function to call with tag value on updates.
- `callWithInitialState` (boolean, optional): If `true`, fetch current value from `/tag_api/info` before subscribing. Default: `false`.

**Unsubscribe:** Pass `null` for either `tagname` or `callback` to unsubscribe the previous subscription.

```javascript
// Subscribe with initial state
mgr.setSubscription("myTag", "/sensors/temperature", (value) => {
  console.log("Temperature:", value);
}, true);

// Unsubscribe by name
mgr.setSubscription("myTag", null, null);
```

#### `destroy()`

Unsubscribe all subscriptions managed by this instance.

```javascript
mgr.destroy();
```

#### `populateTagsDatalist(datalist, filterFunction)`

Fetch available tag points and populate an HTML `<datalist>` element.

- `datalist` (HTML Objet): The datalist to update.
- `filterFunction` (function, optional): Filter function receiving tag info object. Return `true` to include the tag.

```javascript
// Populate datalist with all tags
await mgr.getTagsDatalist("tag-list");

// Populate datalist with only numeric tags
await mgr.getTagsDatalist("numeric-tags", (tag) => tag.valueType === "numeric");
```

## Example

```javascript
import { TagSubscriptionManager } from "/static/js/widget.mjs";

const mgr = new TagSubscriptionManager();

// Display temperature value
const display = document.getElementById("temp-display");
mgr.setSubscription("temp", "/sensors/temperature", (val) => {
  display.textContent = val.toFixed(1) + "°C";
}, true);

// Cleanup on page unload
window.addEventListener("beforeunload", () => mgr.destroy());
```