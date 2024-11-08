import os
import weakref

import structlog
from scullery import scheduling

from kaithem.src import modules, modules_state, pages, unitsofmeasure, util
from kaithem.src.modules_state import in_folder
from kaithem.src.util import url

logger = structlog.get_logger(__name__)


def urlForPath(module, path):
    return (
        "/modules/module/"
        + url(module)
        + "/resource/"
        + "/".join(
            [
                url(i.replace("\\", "\\\\").replace("/", "\\/"))
                for i in path[0].split("/")[:-1]
            ]
        )
    )


def getDesc(module):
    try:
        return module["__metadata__"]["description"]
    except Exception:
        return "No module description found"


def sorted_module_path_list(name: str, path: list):
    return sorted(
        sorted(modules_state.ls_folder(name, "/".join(path))),
        key=lambda x: (
            modules_state.ActiveModules[name][x]["resource_type"],
            x,
        ),
    )


def sorted_module_file_list(name: str, path: list):
    """Yields (name, full resourcename, mtime, size)"""

    p = os.path.join(
        modules_state.getModuleDir(name), "__filedata__", "/".join(path)
    )
    if not os.path.isdir(p):
        return []
    lst = os.listdir(p)

    lst = sorted(lst)

    for i in lst:
        f = os.path.join(p, i)
        try:
            rn = i
            if path:
                rn = "/".join(path) + "/" + i
            if not os.path.isfile(f):
                continue
            yield (i, rn, os.path.getmtime(f), os.path.getsize(f))
        except Exception:
            logger.exception("Failed to get file info")


def breadcrumbs(path):
    temp_p = ""
    for i in path.split("/"):
        temp_p += f"{i}/"
        yield (i, temp_p[:-1])


def get_resource_label_image_url(module: str, path: str):
    data = modules_state.ActiveModules[module][path]

    mf = modules_state.getModuleDir(module)
    mf = os.path.join(mf, "__filedata__/media")
    fn = os.path.join(mf, data["resource_label_image"])
    if os.path.isfile(fn):
        return f"/modules/label_image/{url(module)}/{url(path)}?ts={os.path.getmtime(fn)}"


module_page_context = {
    "si_format_number": unitsofmeasure.si_format_number,
    "url": util.url,
    "external_module_locations": modules.external_module_locations,
    "getModuleHash": modules_state.getModuleHash,
    "getModuleWordHash": modules_state.getModuleWordHash,
    "pages": pages,
    "unitsofmeasure": unitsofmeasure,
    "util": util,
    "scheduling": scheduling,
    "modules_state": modules_state,
    "modules": modules,
    "os": os,
    "weakref": weakref,
    "getDesc": getDesc,
    "in_folder": in_folder,
    "urlForPath": urlForPath,
    "sorted_module_path_list": sorted_module_path_list,
    "sorted_module_file_list": sorted_module_file_list,
    "hasattr": hasattr,
    "breadcrumbs": breadcrumbs,
    "get_resource_label_image_url": get_resource_label_image_url,
}
