# Kaithem Contributions policy(Nov 3 2016)

## Code quality

Any of the following will cause your contribution to be modified heavily or rejected entirely:

* Writing anything to disk unless absolutely needed without the user sending an explicit command
* *Lack of comments*. This one is important, keep all code well commented
* Large embedded resources(Try to use as much compression as possible on sound and images)
* Dependance on the cloud
* Excessive resource usage
* Excessive fancy JS or web design techniques of any kind, especially endless scrolling, and slow single page apps.
* Required dependancies on anything that is not pure python
* Lack of cross platform compatibility
* Lack of error handling(Code is expected to detect errors and automatically retry)
* Reliance on keyboard shortcuts or terse command sequences
* Unnecessary use of "show more" buttons instead of immediate display.
* Unneeded use of nonstandard file formats. In particular, config files should be YAML, INI, \n separated, or plain text.


Keep in mind that Kaithem is intended to be able to run unattended for months. If your code requires doing anything manual to recover from an error, it doesn't belong here.

This includes errors such as cables being unplugged and then plugged back in, etc.

Any unexpected condition should be reported or logged in some way(Keeping in mind rule #1 about not writing to disk without just cause)

This draft coding standards document covers the general idea, but it is a work in progress early draft and subject to change: https://github.com/EternityForest/standards/blob/master/drafts/open_project_guidelines.md

## Relicensing

The project is currently reserving the right to create proprietary forks or this project. Such forks will likely be special-purpose and
the main Kaithem project will likely continue to be GPLv3 or perhaps some other more permissive license. Please understand that
any code you submit for inclusion in this project may be included in proprietary software, relicensed, sublicensed, or any number of other things.

## Contributions containing third-party code

The project, as of November 2016, allows contributions containing third party code, provided that: any snippets included inline are properly
attributed, even where not legally neccesary(Public domain code must include a comment linking to the source if the author is known).

 Similarly, for every piece of third party code longer than 15 lines, and any image, sound, or other creative work, an additional entry shall be created in the credits on the about page,
and included with the commit that introduces the change.

In addition, the third-party material must be licensed under one of:
* Any version of the GNU Lesser General Public License
* Any version of The Apache license; The New or revised BSD or MIT licenses
* The WTFPL, CC0, Public domain, or similar public domain equivalent
* The SIL Open Font License
* Any version of Creative commons Attribution that allows both commercial use and derivative works


## Contributor License Agreement
All original contributions to this project(Except for code that is marked with one of the above approved licenses), are to be considered dedicated to the public domain under CC0. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.

This agreement does not affect original contributions that are clearly marked with a specific license, and third party code is obviously unaffected.
