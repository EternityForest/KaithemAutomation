import quart

from kaithem.src import modules_state, pages, quart_app

searchable = {"event": ["setup", "trigger", "action"], "page": ["body"]}


def searchModules(search, max_results=100, start=0, mstart=0):
    pointer = mstart
    results = []
    x = [None, None]
    for i in sorted(modules_state.ActiveModules.keys(), reverse=True)[mstart:]:
        x = searchModuleResources(i, search, max_results, start)
        if x[0]:
            results.append((i, x[0]))
        max_results -= len(x[0])
        start = 0
        pointer += 1
        if not max_results:
            return (results, max(0, pointer - 1), x[1])
    return (results, max(0, pointer - 1), x[1])


def searchModuleResources(modulename, search, max_results=100, start=0):
    search = search.lower()
    m = modules_state.ActiveModules[modulename]
    results = []
    pointer = start
    for i in sorted(m.keys(), reverse=True)[start:]:
        if not max_results > 0:
            return (results, pointer)
        pointer += 1
        if m[i]["resource_type"] in searchable:
            if search in i.lower():
                results.append(i)
                max_results -= 1
                continue
            for j in searchable[m[i]["resource_type"]]:
                x = str(m[i][j]).lower().find(search)
                if x > 0:
                    results.append(i)
                    max_results -= 1
                    break
    return (results, pointer)


@quart_app.app.route("/modules/search/<module>", methods=["POST"])
async def search(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    kwargs = dict(await quart.request.form)
    kwargs.update(quart.request.args)
    start = mstart = 0
    if "mstart" in kwargs:
        mstart = int(kwargs["mstart"])
    if "start" in kwargs:
        start = int(kwargs["start"])

    @quart.copy_current_request_context
    def f():
        if not module == "__all__":
            return pages.get_template("modules/search.html").render(
                search=kwargs["search"],
                name=module,
                results=searchModuleResources(
                    module, kwargs["search"], 100, start
                ),
            )
        else:
            return pages.get_template("modules/search.html").render(
                search=kwargs["search"],
                name=module,
                results=searchModules(kwargs["search"], 100, start, mstart),
            )

    return await f()
