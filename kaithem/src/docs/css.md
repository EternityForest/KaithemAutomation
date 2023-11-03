# The Kaithem CSS Spec

*anything* not listed here is internal use only.


## Semantic Annotations

Apply these to pretty much anything.

### .help

This item conveys help text. May be hidden in some user preference modes.  Must NOT contain essential functional content.
In particular, Fugit hides help text as it interferes with the cyberpunk look.


## Components

### .window

A large pane, generally with a border and a background.  May have a header and footer.

### .tool-bar

A horizontal bar of items that may contain p, a, button, input, label, input inside label, select, and headings.
May be located anywhere. Themes will usually join all the items together.  It is a flex element that reflows.

### .card

A div styled like a typical UI card.  May contain a header and a footer.  Should not contain text directly because it has no padding.

### .button

Make a link look like it's a button.


## Utilities

### .undecorated
Remove borders, backgrounds, shadows, and backdrop filters.

### .flex
Makes a class into a flex container. It will wrap, and row orientation.  Use this to hold
a lot of cards or other elements, when you'd rather just leave it up to the theme how to lay them out.

Margins or gaps will be added to child elements.

### .scroll

The element is a scroll box. It will stay smaller than the viewport, and show scrollbars for content within.


## Decorative Images

Give a place for the theme to fill in purely decorative content.

### .decorative-image

Use with another of the decorative image classes.

Apply one of these classes to a div.  Unless the theme enables the images, they show as display:none

```
.decorative-image-main
.decorative-image-login
.decorative-image-settings
.decorative-image-h-bar
.decorative-image-corner-ur
```

## Variables

We only use variables for stuff that is repeated a lot and can't be done better just with an override.


### --fg
Text color

### --graphical-fg
Nontext graphic foreground

### --border-radius

### --border-color
