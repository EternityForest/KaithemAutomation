---
allow-origins: ['*']
allow-xss: false
auto-reload: false
auto-reload-interval: 5.0
dont-show-in-index: false
mimetype: text/html
no-header: false
no-navheader: true
require-method: [GET, POST]
require-permissions: []
resource-timestamp: 1568502504739599
resource-type: page
template-engine: markdown

---
A Markdown Page
===============

## Intro
With the display markdown option set in options, the text of the page body
is rendered as markdown without any Mako preprocessing. Useful for help files,
or using Kaithem as a CMS.

The markdown is github-flavored, and if you look at the actual data on the filesystem, they are stored in .md files, with a YAML header,
and can easily be edited in standard text editors that support it.


## Security

This uses Showdown.js! There is NO sanitization. Treat markdown code as you would raw
HTML, it can contain any HTML tag it wants, and only trusted users should be writing it.


## Cool GFM Stuff

### Horizontal Rules(Why aren't these popular anymore?')

Three or more...

---

Hyphens

***

Asterisks

___

Underscores
