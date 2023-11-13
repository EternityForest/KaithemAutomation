# barrel.css
A CSS Framework aiming to be as opinionated as possible for maximum restyling possibilities.

It is a combination of classless styles, a mix of high and low level utilities, and a tiny selection of components.

It supports automatic dark/light theme switching with the system preference, desktop, mobile, and also aims to work as well as possible in print media, especially if you use extra hint classes.  

It's simple enough that it should work on old browsers, but the colors might not look right.  Update your browsers!

This is used as the internal KaithemAutomation CSS framework.  See it[(Here on Github Pages!](https://eternityforest.github.io/barrel.css)

Note that the preview is of this master branch, not any particular release.

When printing, Barrel currently overrides the styles automatically, with a white foreground, flat background,
the theme Serif font, and the URLs displayed after all links.



## Alt themes
Because of weirdness with css variables, all of the alt themes folders must be in the foler with barrel.css itself.  Include barrel.css before
your theme folder.

If you want to put the theme folder elsewhere. just use relative URLs for --bg and the fonts.

Please note: Nord is an adaptation of the Nord Theme, which is MIT licensed, not public domain.
The font file for Fugit is under it's own free license. Images should all be CC0.


## Meta tag

You need this customary tag in your HTML or it doesn't scale right on mobile.
`<meta name="viewport" content="width=device-width, initial-scale=1.0">`

## Semantic Annotations

Apply these to pretty much anything.

### .help

This item conveys help text. May be hidden in some user preference modes.  Must NOT contain essential functional content.
In particular, Fugit hides help text as it interferes with the cyberpunk look.

### .warning, .danger

Levels of badness that should make text red and such.


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

### pre.poem
All child paragraphs have centered text and preserved white space, display centered, generally make
a pre look nice for poetry.

## Utilities

### .round-feathered

Make an image smoothly fade out around the edges.

### .paper
This object should have it's own background, it is like a popup you're going to put over something else.

### .pagebreak
Insert a page break before this element

### .nobreaks
Try not to break this element.  Browsers appear to still do so if necessary, but avoid if possible.

### .noprint
Do not print this element.

### .print-exact
The background color of this and child elements are meaningful, don't remove them when printing.

### .rounded
Round the corners with the default global border-radius.

### .undecorated
Remove borders, backgrounds, shadows, and backdrop filters.

### .flex-row
Makes a class into a flex container. It will wrap, and have row orientation with margin between elements.
The theme is allowed to do whatever else it wants here to make items look nice, it assumes you're doing something
simple like a card collection.

### .flex-col
Same as above but flex as columns.

### .font-normal
Normal text, not bold or italic. Useful in something like a block quote.

### .nogaps
Set flex gap to zero, set all children to have zero margins.

### .scroll

The element is a scroll box. It will stay smaller than the viewport, and show scrollbars for content within.

### .inline
Makes an element inline.  When combined with .block gives inline block. 
When combined with .flex, gives .inline-flex.

May be used on .tool-bar to make it inline.

### .block
Makes it a block.

### .flex
display: flex.

### .padding
The element will have a reasonable theme dependent amount of padding.

### .padding-bottom
Add padding just to bottom.  Useful for fixing scrollbar showing up
when not needed.

### .margin
The element will have a reasonable theme dependent amount of margin.

### .align-left, .align-center, .align-right
These apply to both text content, and flex items.

### .right, .left
Uses the margin: auto trick to move element to the side

### .float-left, .float-right
Uses CSS float.  Probably not what you want unless you are wrapping text.

## Sizing Utilities

### col-1 through col-12

These elements will take be the given fraction(out of 12 columns) of the parent.
Does not use CSS grids, just sets width.  The size will be a little smaller than the given size, for nice margins.

Works correctly with nogaps.

### w-1rem through w-24rem
Options are 1,2,4,6,12, and 24.  Sets width, and flex-basis, if applied to a child of
a .flex-row element.

### w-full
100% width, flex-basis 100%, border-box sizing.

### w-sm-full
This represents the full width of a small screen. The size is not an exact size, it represents
"full width on mobile, and a nice sidebar width on a large screen".

### .w-sm-quarter and .w-sm-half
These also exist.


### .h-1rem to .h-60rem
Used for fixed heights. The sizes are 1,2,4,6,12,24,36,48 and 60.  A limited number are chosen
to not bloat things.  They are taken from the Highly Composite Number sequence.  Sets height
and flex-basis(Only for children of flex-col), max still grow or shrink.

### .max-h-1rem to .max-h-60rem
Can be 1,2,4,6,12,24, sets max-height

### .min-h-1rem to .min-h-24rem
Can be 1,2,4,6,12,24, sets min-height


### .max-content and .min-content

Set width, height, and flex basis to follow the max and min content.

### .nogrow and .noshrink
Flex-grow and flex-shrink set to 0

### .grow

Flex-grow set to 1

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
Note that we have a concept of "convex and concave" inputs. Buttons and labels in toolbars are convex, most others are concave. You can set these to flat styles with variables.

By default most variables are calculated, so you probably don't have to change much.
Start with ones higher up in the list!

Note that the base color definitinons change in dark theme.

```css
:root {
    color-scheme: light dark;

    --black-1: #1c1c1c;
    --black-2: #343A40;
    --black-3: #545862;
    --black-4: #5C555D;

    --grey-1: #e5e4e1;
    --grey-2: #f1f1f1;
    --grey-3: #F8F9FA;

    --red: #b92020;
    --yellow: #cea916;
    --green: rgb(0, 158, 0);
    --teal: rgb(116 174 174);
    --blue: rgb(95 111 161);
    --purple: rgb(161, 95, 141);

    --dark-blue: rgb(40 55 102);

    --scrollbar-width: 14px;

    /*Text color*/
    --fg: var(--black-1);
    /*Nontext items like borders*/
    --graphical-fg: var(--black-4);

    /*Headings, links, etc*/
    --accent-color: var(--dark-blue);
    /*Main page bg*/
    --bg: var(--grey-1);
    /*.paper, items*/
    --box-bg: var(--grey-2);
    --highlight-opacity: 25%;

    /*typography*/

    --sans-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
    --serif-font: Iowan Old Style, Apple Garamond, Baskerville, Times New Roman, Droid Serif, Times, Source Serif Pro, serif, Apple Color Emoji, Segoe UI Emoji, Segoe UI Symbol;
    --mono-font: Menlo, Consolas, Monaco, Liberation Mono, Lucida Console, monospace;

    --main-font: var(--sans-font);
    --font-size: 18px;
    --heading-font: var(--main-font);

    /*Spacing*/
    --padding: 12px;
    --gap: 18px;

    /*Borders*/
    --border-color: color-mix(in srgb, var(--graphical-fg) 50%, rgb(0 0 0 / 0%));

    --border-radius: 1.2rem;
    --border-width: 1px;

    /*Inputs, buttons, etc*/
    --control-height: 3ex;
    --control-border-radius: 12px;
    --control-border-width: 1px;

    --3d-highlight: color-mix(in srgb, var(--box-bg) 50%, rgba(241, 241, 241, 0.695));
    --3d-shadow: color-mix(in srgb, var(--box-bg) 50%, rgba(0, 0, 0, 0.101));

    /*3D buttons are mostly transparent with just some highlights and shadows.*/
    --concave-item-bg: linear-gradient(180deg, var(--3d-shadow) 12%, var(--3d-highlight) 88%);
    --convex-item-bg: linear-gradient(180deg, var(--3d-highlight) 0%, var(--3d-shadow) 96%);
    --convex-item-active-bg: var(--concave-item-bg);
    --concave-item-box-shadow: inset 0px 0px 4px 2px #3838381f;

    /*control-bg also applies to small elements like headers*/
    --control-bg: var(--grey-1);
    --control-fg: var(--graphical-fg);

    /*Used for headers, trays, and anything smaller than a box and bigger than a button*/
    --alt-control-bg: color-mix(in srgb, var(--control-bg) 90%, #816e23);
    /*#e1dfd7*/

    --window-box-shadow: none;

    /*Used for tool bars and cards*/
    --item-box-shadow: none;

    /*Below this line you probably don't need to change stuff*/
    /* fg color for warning and danger */
    --highlight-color: var(--teal);
    --success-color: var(--green);
    --warning-color: var(--yellow);
    --danger-color: var(--red);

    --hover-color: color-mix(in srgb, var(--highlight-color) 30%, transparent);

    --control-border-color: color-mix(in srgb, var(--graphical-fg) 35%, rgb(0 0 0 / 0%));

    /*Intensity of table borders is less than normal borders, to balance the density*/
    --table-border-strength: 50%;

    --thin-border: 1px solid var(--border-color);
}
```

## The Color System

### bg
This is a color or image for the whole page

### box-bg
This is the color of windows(Almost all content is supposed to be in a window), and anything with the .paper class.  Cards do not have a background by default.


### fg

Body Text.

### accent-color

Used for the text color of headings, links, and scrollbars

### graphical-fg
Used for icons and borders, but usually "diluted" first with a background color


### control-bg
Used for text areas, plus buttons and inputs when displaying flat. Also used as the base color for scrollbar tracks.


### alt-control-bg
 Used for things you don't directly interact with but act as a container.  Headers and footers are this color.Trays and drag handles should be this color.  Defaults to an automatically created slight variation on the control-bg.

### control-fg
This color is used for buttons and text inputs, and also small indicators and table headings.

### convex-item-bg
Usually a gradient for buttons and labels

### concave-item-bg
used for selects and text boxes.  Concave and convex can be flattened some or all of the time by setting them to the alt-control-bg.


### concave-item-box-shadow
text areas, selects, inputs, and similar, should have an inset box shadow unless the theme is ultra flat.

### border-color
Defaults to a diluted version of the graphical-fg.

### control-border-color
May differ from the border color, defaults to the border color.




### success, warning, danger, and highlight colors

Pure strong base colors used to derive the foreground and background of highlighted elements.

The highlight color is also used for selected text and slider thumbs. 


### Rules
Any fg color except the border color, must always be easily legible on any bg color, except the main bg.

The main bg color does not need to have any particular contrast with anything else.

No two background colors are required to be visually distinct, they are used to make things "look right" but should not be relied on to convey information.  Likewise, no two foreground colors are required to be distinct.

