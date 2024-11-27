import quart
import structlog
import yaml
from quart import copy_current_request_context, request
from scullery import messagebus

from kaithem.src import dialogs, modules, modules_state, pages, quart_app, util
from kaithem.src.util import url

logger = structlog.get_logger(__name__)


@quart_app.app.route("/modules/module/<module>/uploadresource")
async def uploadresourcedialog(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    path = quart.request.args.get("dir", "")

    d = dialogs.SimpleDialog(f"Upload resource in {module}")
    d.file_input("file")
    d.text_input("filename")
    d.submit_button("Submit")
    return d.render(
        f"/modules/module/{url(module)}/uploadresourcetarget",
        hidden_inputs={"dir": path},
    )


@quart_app.app.route(
    "/modules/module/<module>/uploadresourcetarget", methods=["POST"]
)
async def uploadresourcetarget(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    upl = None
    for name, file in (await request.files).items():
        upl = file
    kwargs = await request.form

    if not upl:
        raise RuntimeError("No file uploaded")

    @copy_current_request_context
    def f():
        f = b""

        path = kwargs["dir"].split("/") + [kwargs["filename"].split(".")[0]]
        path = "/".join([i for i in path if i])

        while True:
            d = upl.read(8192)
            if not d:
                break
            f = f + d

        d2 = yaml.load(f.decode(), yaml.SafeLoader)

        if path in modules_state.ActiveModules[module]:
            raise RuntimeError("Path exists")

        modules_state.rawInsertResource(module, path, d2)
        modules.handleResourceChange(module, path)
        return quart.redirect(f"/modules/module/{util.url(module)}")

    return await f()


@quart_app.app.route("/modules/module/<module>/download_resource/<obj>")
def download_resource(module, obj):
    pages.require("view_admin_info")
    if (
        modules_state.ActiveModules[module][obj]["resource_type"]
        in modules_state.additionalTypes
    ):
        modules_state.additionalTypes[
            modules_state.ActiveModules[module][obj]["resource_type"]
        ].flush_unsaved(module, obj)
    r = quart.Response(
        yaml.dump(modules_state.ActiveModules[module][obj]),
        headers={"Content-Disposition": f'attachment; filename="{obj}.yaml"'},
    )
    return r


# This lets the user download a module as a zip file with yaml encoded resources
@quart_app.app.route("/modules/yamldownload/<module>")
def yamldownload(module):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    fn = util.url(
        f"{module[:-4]}_{modules_state.getModuleWordHash(module[:-4]).replace(' ', '')}.zip"
    )

    mime = "application/zip"
    try:
        d = modules_state.getModuleAsYamlZip(
            module[:-4] if module.endswith(".zip") else module,
        )
        r = quart.Response(
            d,
            mimetype=mime,
            headers={"Content-Disposition": f"attachment; filename={fn}"},
        )
        return r
    except Exception:
        logger.exception("Failed to handle zip download request")
        raise


@quart_app.app.route("/modules/uploadtarget", methods=["POST"])
async def uploadtarget():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    # Can't actuslly use def in a for loop usually but it;s fine since there;s only one
    for name, file in (await request.files).items():

        @copy_current_request_context
        def f():
            modules_state.recalcModuleHashes()
            modules.load_modules_from_zip(
                file, replace="replace" in request.args
            )

        await f()

    messagebus.post_message(
        "/system/modules/uploaded", {"user": pages.getAcessingUser()}
    )
    return quart.redirect("/modules")
