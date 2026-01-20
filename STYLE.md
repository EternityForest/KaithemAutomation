# Kaithem Coding Style Guide

## Use the dev tools

* Avoid powerful macros, customization-oriented languages like FORTH, preprocessors, and other things that debuggers, linters, and formatters have trouble with.

* Don't hide dynamic typing behind string lookups , make sure the static analyzer always knows what function you're calling or objects you're getting.

* Assume readers have a modern IDE.  Prioritize the dev experience with modern tools over the raw code itself.

* Make maximum use of the tools.  Make your types as narrow as possible, aim for zero compiler warnings

* Apply type constraints to specific properties in JSON-like data, using features like TypedDict

* Use Git branches in a disciplined way and write proper commit messages.

* Use "accessory" tools like pre-commit, direnv, make, Atuin, etc, rather than piles of random scripts

* Auto format code with the most common formatter in the most common configuration, and be done with it.

* Secret scanning must be used on repos

* Do not use star imports in Python or similar features.

## Standardization

* Use common file formats, protocols, languages, and libraries when appropriate.

* Even if a protocol or format is only used by one other project, if it fits your needs, it's still better than a completely incompatible original system.

* The license should be a common standard one like MIT or GPL, specified with SPDX expressions.

* Version numbers should use Semantic Versioning.

* User created content should be version controllable and ideally sync-able with file sync tools

* To decrease fragmentation and avoid depending to on small obscure vendors, generally prefer multifunctional, one size fits all toold

* Do things in common, boring ways, unless there is a reason to do otherwise, try to make sure as much of the system as possible is tested and proven.

* Think about the user and experience in the context of other relevant tools and processes used alongside the project

* Don't spend time supporting unusual configurations you don't actually need, like ancient EOL OS versions or big endian CPUs.

* Avoid depending on system libraries or any resources that aren't managed as part of an isolated environment.

* Don't make unnecessary wrapper layers around things that are already de facto standards, directly expose them.

* Don't modify and fork things, unless you're contributing to upstream, and don't build things that users would have to modify to use

* Future proof things.  Don't use stuff that won't be around in ten years, if possible, migrate early if a technology is very clearly on it's way out

* People like free stuff, if something costs money, it's less likely to become "the standard", unless there are no free competitors.

## Safety

* Worse is *Not* Better, cover the edge cases

* Keep user and hardware error in mind

* Always have undo buttons or confirmation for critical actions

* Validate inputs, and functions that cause persistent effects.

* Do not use gestural UIs that can be easily triggered accidentally, without an easy and obvious way to fully undo the action

* Avoid relying on tacit knowledge or unconscious competence in general, keep things explicit, procedural, and in conscious control.

* Keep developer error in mind, remove opportunities to fail where possible.

* Reliability always comes first, even before performance and simplicity

* Be mindful of network usage and SSD wear, assume devices may need to run on cheap SD cards with unreliable 1MBPs wifi.

* Aim for very high quality test coverage, covering all the hypothetical bugs you can readily think of

* Prefer popular and widely trusted libraries over original code.

* Put the minimum amount of trust possible in systems, use hardware or inherent fail-safes for anything that could cause injury

* Hackers can't steal data if you do not have it in the first place. Leave dealing with senstive data to specialists or cloud services, unless you actually need it for your core functionality.

* Trust LLM generated code exactly as much as human written code, which is to say not at all, your reviews and tests should be thorough enough to make "trust" almost unnecessary.

* Mind the bus number.  No one person or vendor should be critical.

* Avoid manual changes to live systems. Servers should be updated atomically from a single source of truth, not maintained and curated over time.

* When one-off changes are needed, do so via a testable script or safe UI tht has a preview and undo.

* Avoid things that create an appearance of being associated with suspicious activity, such as P2P technology that may be flagged by AI bots

* Things should still work offline

## User Experience

* There should be a quick start guide,  It should take less than five minutes to figure out what the software does, if you want to use it, and how to set it up

* Aim for zero unpredictable maintenance.

* If a technology takes more than a few minutes to set up and does not "just work", be suspicious that it may continue to require attention in the future.

* Do not do anything that requires unusual system configuration outside the app itself, such as installing self signed certificates or enabling some custom package repo

* Don't include Easter eggs, but non-hidden purely decorative elements, like splash animations, are perfectly fine.

* Aim for discoverability.  Nobody should need to reread the manual every two weeks when they need to do an uncommon task

* Don't waste time reinventing features that already exist in a technology users already have, such as chat or calendars, unless there is specific value in tight integration.

* Remember that liability protection is almost as important as actual security and reliability, don't expect users to do anything they couldn't justify to the security guy at a major bank

* Even tiny amounts of unreliability are unacceptable to many users, especially if they are not protected from liability.  Do not expect them to do something like hosting their own email and risking getting fired for that choice if the server fails and they miss an important message.

* Make heavy use of the "sidebar inspector" pattern for intuitiveness and consistency.

* Use modal dialogs rather than littering stuff all over the pages.

* Create guided experiences where everything you need to know is visible, rather than expecting the user to be one step ahead of the machine.

## Aesthetics of the Architecture

* Design your APIs as if we're working on am extremely popular library, used by millions of developers

* Holonomic control: Maintain options and the ability to arbitrarliy modifiy parameters without affecting other parts of the system, except for industry standards that are extremely unlikely to change for the life of the project.

* Avoid making behavior dependent on inherent properties of the hardware rather than active control

* Minimize the amount of information a user or developer must store in their head at one time to effectively work with the system

* Prefer declarative over imperative. Interfaces should expose the minimum amount of power and flexibility, and encapsulate as much logic as possible

* Have a pre-canned workflow for common tasks, rather than supporting every imaginable common workflow. There should be One Obvious Way To Do It.

* Don't create "lite" versions of APIs for quick hacky use cases, unless the "pro version" API is significantly difficult to use.  Hacks are out of scope.

* Simplicity is a valuable heuristic, but not the primary priority.

* Minimize the need for documentation: use patterns people already know.

* If it's hard to explain, it's a bad idea(ZoP)

* Don't repeat yourself, and don't do the same thing in multiple ways, such as using both client and server side templating

* Don't manually keep things in sync, or manually copy things from the output of the same command regularly.  Automate everything you can.

* GUI support and performance from day 1, don't build things you know are going to be slow, or lock yourself into feed forward pipeline models that provide a poor GUI experience

* Don't have more than a few layers of arbitrary remappings, just specify the file should always be named X, rather than having three layers of config pointing to it.

* Don't create "Pseudo protocols", which are really "build your own protocol kits". Just say "There must be an icon file in a supported format" not "There must be a schema that maps files to roles and implementations may define an icon role"

* Don't break abstraction boundaries. If you find yourself carefully studying the bit patterns of IEEE floats, try to find a different approach that is agnostic to those details

* Don't hardcode empirically measured constants.  Assume the time a server takes to respond, or the size or the display, or the sensitivity threshold a light sensor needs, will change unpredictably.

* In particular, always assume screen size is dynamic.

* Don't store more than two or three items in a tuple, prefer structured objects with named keys.

* Do not have functions that are longer than one page

* Generally try to avoid mutable global variables.

* Use modern versions of APIs, prefer things like ESM modules over things like regular JS files.

* Try to create single sources of truth

* Make heavy use of schemas, schema validation, and schema based editors.

* Avoid external documentation that might get out of sync, document inline where possible

## Details

* 80 character line limits, always, regardless of modern display size.  It's hard to read wide text, and doesn't fit on screen once you add all the extra IDE panes.

* Spaces not tabs.  We don't need two different whitespace chars.

* No hand formatted code.  Just let the formattter do it and move on.

* No single letter or extremlely terse names except in absolutely trivial functions.

* Use assertions generously, actively look for places they might be inserted.

* While() loops must have safety counters or upper bounds unless intended to run forever.

* Functions should not just ignore incorrect inputs, raise exceptions if something is not working as intended.

* Do not explicitly silence true errors without actually handling them properlt.  No except: pass

* Avoid returning mutable references to persistent state, unless you intend for the caller to modify the persistent state

## Testing

* Code must have high quality test coverage, even if testability adds significant complexity

* AI generated tests are better than no tests, they at leatkeep behavior consistent even if they can't demonstrate correctness by themselves.

* Visible features should have end to end tests

* Tests should check that mutable state is not corrupt, especially watching out for multiple references to objects that should be copied

* Tests should cover any obvious mistakes you can easily imagine future devs *could* make

