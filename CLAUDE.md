# CLAUDE.md

- Output only what is asked.
- If uncertain: say UNKNOWN or omit. Do not guess.
- Bullets > prose. Prefer deletion over verbosity.
- Do not rewrite whole files; make surgical edits.
- Read STYLE.md when planning large changes, it contains guidance on project UX and dev practices.

## Architecture

* Plugins in kaithem/src/plugins get discovered and imported
* We use a Quart based web UI
* pages.require("permission_name") is used to secure those endpoints
* New dynamic UI pages compile with Vite as a multi page app
* Very simple UI pages can use server side Jinja2, but Mako is deprecated legacy work
* Vite sources are scattered everywhere but output to /static/vite
* /static/vite URLs map to /kaithem/data/static/vite

## Links / Authority

- STYLE.md

## Stop Conditions

- Missing repo context → ask / stop
- Destructive ops (rm, force push, prod deploy, publish to pypi) → stop
