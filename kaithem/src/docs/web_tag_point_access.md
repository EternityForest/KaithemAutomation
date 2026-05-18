# Tag Point Access API

Web frontend API for subscribing to and accessing tag point values in Kaithem.


If you are developing an external plugin, copy and paste
`kaithem/src/js/types-widget.d.ts` and add it to  "typeRoots" in tsconfig, to get interactive type hints in your IDE.




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

- `datalist` (HTMLDataListElement): The datalist to update.
- `filterFunction` (function, optional): Filter function receiving a CompactTagDescription object. Return `true` to include the tag.

The CompactTagDescription object has these properties:
- `name`: Tag point name (e.g., "/my/tag")
- `type`: Tag type ("number", "string", "object", "binary")
- `subtype`: Additional subtype information
- `writable`: Whether the tag is writable
- `canWrite`: Whether the current user can write to this tag

```javascript
// Populate datalist with all tags
await populateTagsDatalist(document.getElementById("tag-list"));

// Populate datalist with only numeric or string tags
await populateTagsDatalist(document.getElementById("numeric-tags"), (tag) => {
  return tag.type === 'number' || tag.type === 'string';
});
```

#### `getTagMetadata(tagname)`

Fetch full metadata for a specific tag point, including the current value.

- `tagname` (string): Tag point name (e.g., "/my/tag")

Returns a Promise resolving to a FullTagDescription object with these properties:
- `writePermission`: Whether the current user can write to this tag
- `type`: Tag type ("number", "string", "object", "binary")
- `subtype`: Additional subtype information
- `lastVal`: Current value of the tag
- `min`, `max`, `high`, `low`, `unit`: Numeric tag specifics (if applicable)

```javascript
import { getTagMetadata } from "/static/js/widget.mjs";

const metadata = await getTagMetadata("/sensors/temperature");
console.log("Current temperature:", metadata.lastVal);
console.log("Unit:", metadata.unit);
console.log("Can write:", metadata.writePermission);
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