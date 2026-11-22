from __future__ import annotations

import html
import os
import re
import shutil
import threading
from typing import Any, override
from urllib.parse import quote

import structlog
from asgiref.typing import (
    Scope,
)

from kaithem.api import api_keys
from kaithem.api import modules as modules_api
from kaithem.api.proxies import PathProxy
from kaithem.api.resource_types import (
    BasicResourceType,
    ResourceTypeRuntimeObject,
    resource_type_from_schema,
)
from kaithem.src import modules_state

from .appconfig import ConfigError, ContainerAppConfig, load_config
from .constants import (
    APP_PRIORITY,
    APP_RESOURCE_TYPE,
    DEFAULT_PERMISSIONS,
    DEV_PATH_SUFFIX,
    INSTANCE_PRIORITY,
    INSTANCE_RESOURCE_TYPE,
)
from .runtime import ContainerRuntime, sandbox_dir
from .static_apps import StaticFilesApp

logger = structlog.get_logger(__name__)

#: Shipped starter projects copied by the "Copy Template" action.
TEMPLATES: dict[str, str] = {
    "bun-lit-static": os.path.join(
        os.path.dirname(__file__), "templates", "bun-lit-static"
    ),
    "uv-python": os.path.join(
        os.path.dirname(__file__), "templates", "uv-python"
    ),
}

#: Template used when the client does not name one.
DEFAULT_TEMPLATE = "bun-lit-static"

#: Legal characters in a URL slug (also the schema pattern below).
_SLUG_PATTERN = r"^([a-z][a-z0-9-_]*)?$"
_SLUG_RE = re.compile(_SLUG_PATTERN)

APP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "default": ""},
        "permissions": {
            "type": "array",
            "items": {"type": "string"},
            "default": list(DEFAULT_PERMISSIONS),
        },
        "service_user": {"type": "string", "default": "__guest__"},
    },
    "additionalProperties": False,
}

APP_DEFAULT: dict[str, Any] = {
    "title": "",
    "permissions": list(DEFAULT_PERMISSIONS),
    "service_user": "__guest__",
}

INSTANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "app": {"type": "string", "default": ""},
        "name": {"type": "string", "default": "", "pattern": _SLUG_PATTERN},
        "title": {"type": "string", "default": ""},
        "boot": {"type": "boolean", "default": True},
    },
    "required": ["app"],
    "additionalProperties": False,
}

INSTANCE_DEFAULT: dict[str, Any] = {
    "app": "",
    "name": "",
    "title": "",
    "boot": True,
}


def _require_slug(value: str, what: str) -> str:
    value = value.strip()
    if not _SLUG_RE.match(value):
        raise ValueError(
            f"{what} {value!r} must be a URL slug of lowercase letters, "
            "digits and dashes"
        )
    return value


def resolve_name(configured: str | None, resource: str) -> str:
    """Return the URL slug for an instance, defaulting to its resource."""
    slug = (configured or "").strip() or resource
    return _require_slug(slug, "Instance name")


def _project_paths(module: str, resource: str) -> tuple[str, str]:
    """Return ``(root, app_folder)`` for an app resource.

    Everything lives under ``__filedata__/<resource>.d`` so the module UI
    shows the whole project tree instead of hiding it in a dot folder.
    """
    root = modules_state.filename_for_file_resource(module, resource + ".d")
    return root, os.path.join(root, "app")


def _instance_data_dir(module: str, resource: str) -> str:
    """Return the persistent data folder for an instance resource."""
    root = modules_state.filename_for_file_resource(module, resource + ".d")
    return os.path.join(root, "data")


def _register_directory_resources(
    module: str, resource: str, children: list[str]
) -> None:
    """Expose the project folders as directory resources.

    Called from ``on_load`` while the modules lock is held, so it must not
    call :func:`modules_state.importFiledataFolderStructure` (which takes
    the same non-reentrant lock).  Inserting the entries directly is safe
    because the loader snapshots the resource list before iterating.
    """
    module_resources = modules_state.ActiveModules.setdefault(module, {})
    base = resource + ".d"
    module_resources.setdefault(base, {"resource": {"type": "directory"}})
    for child in children:
        module_resources.setdefault(
            f"{base}/{child}", {"resource": {"type": "directory"}}
        )


class ContainerAppResource(ResourceTypeRuntimeObject):
    """Runtime state for one ``container_app`` resource."""

    def __init__(self, module: str, resource: str, data: dict[str, Any]):
        self.module = module
        self.resource = resource
        self.data = data
        self.error: str | None = None
        self.config: ContainerAppConfig | None = None
        self.sandbox_runtime: ContainerRuntime | None = None
        self.api_key: api_keys.EphemeralApiKey | None = None
        self.proxy: PathProxy | StaticFilesApp | None = None
        self._dev = False
        self._closed = False

        self.project_root, self.project_folder = _project_paths(
            module, resource
        )

        os.makedirs(self.project_folder, exist_ok=True)
        _register_directory_resources(module, resource, ["app"])
        self._load_sandbox_runtime()

    # -- Setup ----------------------------------------------------------

    @property
    def title(self) -> str:
        return self.data.get("title") or self.resource

    @property
    def dev_prefix(self) -> str:
        """URL prefix the dev runtime is served from."""
        return "/apps/" + _require_slug(
            self.resource + DEV_PATH_SUFFIX, "Dev path"
        )

    def _load_sandbox_runtime(self) -> None:
        """(Re)read ``container-app.toml`` and rebuild the runtime."""
        self._close_runtime()
        try:
            config = load_config(self.project_folder)
        except ConfigError as exc:
            self.config = None
            self.error = str(exc)
            return

        owner = f"app:{self.module}:{self.resource}"
        self.config = config
        self.error = None
        self.sandbox_runtime = ContainerRuntime(
            owner_id=owner,
            project_folder=self.project_folder,
            data_dir=sandbox_dir(owner),
            base_path=self.dev_prefix,
        )
        self.api_key = api_keys.add_ephemeral_api_key(self.service_user)
        self.sandbox_runtime.api_key = self.api_key.key

    @property
    def service_user(self) -> str:
        return self.data.get("service_user") or "__guest__"

    @property
    def permissions(self) -> list[str]:
        return list(self.data.get("permissions") or [])

    def _close_runtime(self) -> None:
        self._unmount()
        if self.sandbox_runtime is not None:
            try:
                self.sandbox_runtime.close()
            except Exception:
                logger.exception("Failed to close container app runtime")
            self.sandbox_runtime = None
        if self.api_key is not None:
            self.api_key.remove()
            self.api_key = None
        self._dev = False

    def _unmount(self) -> None:
        if self.proxy is not None:
            try:
                self.proxy.close()
            except Exception:
                logger.exception("Failed to close container app proxy")
            self.proxy = None

    def _require_runtime(self) -> ContainerRuntime:
        """Gets a runtime and unsures config is new"""
        rt = self.sandbox_runtime
        if rt is None:
            raise RuntimeError(self.error or "Container app is not set up")
        rt.reload_config()
        return rt

    # -- Introspection --------------------------------------------------

    @property
    def status(self) -> str:
        if self._dev:
            return "dev running"
        if self.sandbox_runtime is None:
            return "dev idle"
        return self.sandbox_runtime.status

    @property
    def is_dev(self) -> bool:
        return self._dev

    @property
    def app_kind(self) -> str | None:
        if self.config is None:
            return None
        app = self.config["app"]
        return None if app is None else app["kind"]

    def get_commands(self) -> list[dict[str, Any]]:
        if self.sandbox_runtime is None:
            return []
        return self.sandbox_runtime.get_commands()

    def is_empty(self) -> bool:
        """Return whether the app folder has no project files yet."""
        try:
            return not os.listdir(self.project_folder)
        except FileNotFoundError:
            return True

    def is_built(self) -> bool:
        return bool(self.sandbox_runtime and self.sandbox_runtime.is_built())

    def get_log(self) -> str:
        if self.sandbox_runtime is None:
            return ""
        return self.sandbox_runtime.get_command_log("app")

    def get_environment(self) -> dict[str, str]:
        if self.sandbox_runtime is None:
            return {}
        return self.sandbox_runtime.get_environment()

    def instances(self) -> list[ContainerAppInstanceResource]:
        """Return every loaded instance that runs this app."""
        return _instances_for(self.module, self.resource)

    # -- Control --------------------------------------------------------

    def start_dev(self) -> None:
        """Run the app in dev mode with an ephemeral data folder."""
        runtime = self._require_runtime()
        if self.app_kind is None:
            raise RuntimeError("This project has no app")
        self._mount()
        if self.app_kind == "command":
            runtime.start(dev=True)
        self._dev = True

    def stop_dev(self) -> None:
        """Stop the dev runtime and unmount its preview path."""
        if self.sandbox_runtime is not None:
            try:
                self.sandbox_runtime.stop()
            except Exception:
                logger.exception("Failed to stop container app dev runtime")
        self._unmount()
        self._dev = False

    def run_script(self, name: str) -> None:
        self._require_runtime().run_script(name)

    def stop_script(self, name: str) -> None:
        self._require_runtime().stop_script(name)

    def stop_app(self) -> None:
        """Stop the app from its console toolbar."""
        self.stop_dev()

    def delete_runtime(self) -> None:
        self._require_runtime().delete_runtime()

    def reload(self) -> None:
        """Re-read the project config and remount."""
        if self._dev:
            self.stop_dev()
        self._load_sandbox_runtime()

    def copy_template(self, name: str = DEFAULT_TEMPLATE) -> None:
        """Copy a shipped starter project into an empty app folder."""
        if not self.is_empty():
            raise RuntimeError("Project folder is not empty")
        template_dir = TEMPLATES.get(name)
        if template_dir is None:
            raise ValueError(f"Unknown template {name!r}")
        os.makedirs(self.project_folder, exist_ok=True)
        shutil.copytree(template_dir, self.project_folder, dirs_exist_ok=True)
        self.reload()

    # -- Proxy ----------------------------------------------------------

    def _mount(self) -> None:
        if self.proxy is not None:
            return
        self.config = load_config(self.project_folder)
        runtime = self._require_runtime()
        app = self.config["app"]
        if app is None:
            return
        title = f"{self.title} (dev)"
        if app["kind"] == "command":
            if not app["web"]:
                return
            self.proxy = PathProxy(
                prefix=self.dev_prefix,
                target=runtime.unix_target(),
                title=title,
                permissions=self.permissions,
                module=self.module,
                resource=self.resource,
                request_header_interceptors=[self._inject_api_key],
            )
        else:
            self.proxy = StaticFilesApp(
                prefix=self.dev_prefix,
                source_dir=runtime.static_source_dir(),
                title=title,
                permissions=self.permissions,
                module=self.module,
                resource=self.resource,
            )

    def _inject_api_key(
        self, scope: Scope, user: str, headers: dict[str, str]
    ) -> dict[str, str] | None:
        if self.api_key is None:
            return None
        new_headers = dict(headers)
        new_headers[api_keys.API_KEY_HEADER] = self.api_key.key
        return new_headers

    # -- Teardown -------------------------------------------------------

    @override
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close_runtime()


class ContainerAppInstanceResource(ResourceTypeRuntimeObject):
    """Runtime state for one ``container_app_instance`` resource."""

    def __init__(self, module: str, resource: str, data: dict[str, Any]):
        self.module = module
        self.resource = resource
        self.data = data
        self.error: str | None = None
        self.name = ""
        self.config: ContainerAppConfig | None = None
        self.runtime: ContainerRuntime | None = None
        self.api_key: api_keys.EphemeralApiKey | None = None
        self.proxy: PathProxy | StaticFilesApp | None = None
        self.app_module: str | None = None
        self.app_resource: str | None = None
        self._closed = False

        self.project_folder = ""
        self.data_dir = _instance_data_dir(module, resource)

        _register_instance(self)
        try:
            self.name = resolve_name(self.data.get("name"), resource)
            self._setup()
        except Exception as exc:
            logger.exception(
                "Failed to set up container app instance %s/%s",
                module,
                resource,
            )
            self.error = str(exc)

    # -- Setup ----------------------------------------------------------

    def _setup(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        _register_directory_resources(self.module, self.resource, ["data"])
        app_module, app_resource, app_data = self._resolve_app()
        self.app_module = app_module
        self.app_resource = app_resource

        app_root, self.project_folder = _project_paths(app_module, app_resource)
        config = load_config(self.project_folder)

        owner = f"instance:{self.module}:{self.resource}"
        self.config = config
        self.runtime = ContainerRuntime(
            owner_id=owner,
            project_folder=self.project_folder,
            data_dir=self.data_dir,
            base_path=self.base_path,
        )
        self.api_key = api_keys.add_ephemeral_api_key(
            app_data.get("service_user") or "__guest__"
        )
        self.runtime.api_key = self.api_key.key
        self._mount()

        if self.boots and self.runtime.is_built():
            threading.Thread(
                target=self._boot_start,
                daemon=True,
                name=f"capp-boot-{self.module}-{self.resource}",
            ).start()

    def _resolve_app(
        self,
    ) -> tuple[str, str, dict[str, Any]]:
        spec = str(self.data.get("app") or "").strip()
        app_module, _, app_resource = spec.partition(":")
        app_module = app_module.strip()
        app_resource = app_resource.strip()
        if not app_module or not app_resource:
            raise ValueError("'app' must be a 'module:resource' reference")

        # pyrefly: ignore [bad-assignment]
        resource_type: BasicResourceType = modules_state.resource_types.get(
            APP_RESOURCE_TYPE
        )
        app = None
        if resource_type is not None:
            app = resource_type.runtime_objects.get((app_module, app_resource))
        if app is None:
            raise ValueError(f"No container app {app_module}:{app_resource}")
        return app_module, app_resource, app.data

    def _mount(self) -> None:
        if self.proxy is not None:
            return
        runtime = self._require_runtime()
        self.config = load_config(self.project_folder)

        assert self.config is not None
        app = self.config["app"]
        if app is None:
            return
        title = self.data.get("title") or f"{self.app_resource} ({self.name})"
        if app["kind"] == "command":
            if not app["web"]:
                return
            self.proxy = PathProxy(
                prefix=self.base_path,
                rewrite=[("^/$", "/index")],
                target=runtime.unix_target(),
                title=title,
                module=self.module,
                resource=self.resource,
                request_header_interceptors=[self._inject_api_key],
                permissions_provider=self._permissions_provider,
            )
        else:
            self.proxy = StaticFilesApp(
                prefix=self.base_path,
                source_dir=runtime.static_source_dir(),
                title=title,
                module=self.module,
                resource=self.resource,
                permissions_provider=self._permissions_provider,
            )

    def _inject_api_key(
        self,
        scope: Scope,
        user: str,
        headers: dict[str, str],
    ) -> dict[str, str] | None:
        if scope["type"] == "lifespan":
            return None
        if self.api_key is None:
            return None
        new_headers = dict(headers)
        new_headers[api_keys.API_KEY_HEADER] = self.api_key.key
        return new_headers

    def _permissions_provider(self) -> list[str]:
        """Read the app's current permissions on every request.

        Looking them up live keeps access correct when the app is edited
        while an instance is running, and is robust to load order.
        """
        # pyrefly: ignore [bad-assignment]
        resource_type: BasicResourceType = modules_state.resource_types.get(
            APP_RESOURCE_TYPE
        )
        app = None
        if resource_type is not None:
            assert self.app_module is not None
            assert self.app_resource is not None
            app = resource_type.runtime_objects.get(
                (self.app_module, self.app_resource)
            )
        if app is None:
            return list(DEFAULT_PERMISSIONS)
        return list(app.data.get("permissions") or [])

    def _boot_start(self) -> None:
        try:
            self.start()
        except Exception as exc:
            logger.exception("Failed to start container app instance")
            self.error = str(exc)

    def _require_runtime(self) -> ContainerRuntime:
        if self.runtime is None:
            raise RuntimeError(self.error or "Container app is not set up")
        return self.runtime

    # -- Introspection --------------------------------------------------

    @property
    def base_path(self) -> str:
        return "/apps/" + self.name

    @property
    def boots(self) -> bool:
        return bool(self.data.get("boot", True))

    @property
    def app_kind(self) -> str | None:
        if self.config is None:
            return None
        app = self.config["app"]
        return None if app is None else app["kind"]

    @property
    def is_static(self) -> bool:
        return self.app_kind == "staticfiles"

    @property
    def status(self) -> str:
        if self.runtime is None:
            return "stopped"
        if self.is_static:
            return "running" if self.runtime.is_built() else "stopped"
        return self.runtime.status

    def is_running(self) -> bool:
        if self.runtime is None:
            return False
        if self.is_static:
            return True
        return self.runtime.status in ("running", "loading")

    def is_built(self) -> bool:
        return bool(self.runtime and self.runtime.is_built())

    def get_commands(self) -> list[dict[str, Any]]:
        if self.runtime is None:
            return []
        return self.runtime.get_commands()

    def get_log(self) -> str:
        if self.runtime is None:
            return ""
        return self.runtime.get_command_log("app")

    def get_environment(self) -> dict[str, str]:
        if self.runtime is None:
            return {}
        return self.runtime.get_environment()

    # -- Control --------------------------------------------------------

    def start(self) -> None:
        if self.runtime is None:
            raise RuntimeError(self.error or "Container app is not set up")
        if self.app_kind is None:
            raise RuntimeError("This project has no app")
        if self.is_static:
            return
        self.runtime.start(dev=False)

    def stop(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()

    def stop_app(self) -> None:
        """Stop the app from its console toolbar."""
        if self.runtime is not None:
            self.runtime.stop_script("app")

    def run_script(self, name: str) -> None:
        self._require_runtime().run_script(name)

    def stop_script(self, name: str) -> None:
        self._require_runtime().stop_script(name)

    def delete_runtime(self) -> None:
        self._require_runtime().delete_runtime()

    def reload(self) -> None:
        """Re-read the app config and rebuild this instance's runtime."""
        self._teardown_runtime()
        self.error = None
        try:
            self._setup()
        except Exception as exc:
            logger.exception("Failed to reload container app instance")
            self.error = str(exc)

    # -- Teardown -------------------------------------------------------

    @override
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _unregister_instance(self.module, self.resource)
        self._teardown_runtime()

    def _teardown_runtime(self) -> None:
        if self.proxy is not None:
            try:
                self.proxy.close()
            except Exception:
                logger.exception("Failed to close container app proxy")
            self.proxy = None
        if self.runtime is not None:
            try:
                self.runtime.close()
            except Exception:
                logger.exception("Failed to close container app runtime")
            self.runtime = None
        if self.api_key is not None:
            self.api_key.remove()
            self.api_key = None


# -- Instance registry --------------------------------------------------
#
# Instances are tracked here, guarded by a lock, so an app can find the
# instances that run it without iterating the resource type's live dict
# from another thread.

_instances: dict[tuple[str, str], ContainerAppInstanceResource] = {}
_instances_lock = threading.Lock()


def _register_instance(obj: ContainerAppInstanceResource) -> None:
    with _instances_lock:
        _instances[(obj.module, obj.resource)] = obj


def _unregister_instance(module: str, resource: str) -> None:
    with _instances_lock:
        _instances.pop((module, resource), None)


def _instances_for(
    app_module: str, app_resource: str
) -> list[ContainerAppInstanceResource]:
    with _instances_lock:
        return [
            obj
            for obj in _instances.values()
            if obj.app_module == app_module and obj.app_resource == app_resource
        ]


# -- Resource registration ----------------------------------------------


def _app_after_create(
    obj: ContainerAppResource, module: str, resource: str
) -> None:
    """Create a default instance when an app is created in the UI.

    Only runs for interactive creation, never for an imported module, so a
    shared project zip keeps exactly the instances its author defined.
    """

    instance_name = f"{resource}_default"
    with modules_api.modules_lock:
        if instance_name in modules_state.ActiveModules.get(module, {}):
            return
        data = {
            "app": f"{module}:{resource}",
            "name": instance_name,
            "title": "",
            "boot": True,
        }
        try:
            modules_api.insert_resource(
                module,
                instance_name,
                {
                    "name": instance_name,
                    "data": data,
                    "resource": {"type": INSTANCE_RESOURCE_TYPE},
                },
            )
        except ValueError:
            # Someone created it between our check and the insert.
            logger.debug("Default instance already exists")


def _app_blurb(obj: ContainerAppResource, module: str, resource: str) -> str:
    """Render the module page summary for a container app."""
    parts = [
        '<div class="container-app-blurb">',
        '<p data-testid="container-app-status">'
        f"Status: {html.escape(obj.status)}</p>",
    ]
    if obj.error:
        parts.append(
            '<div class="text-red" data-testid="container-app-error">'
            f"{html.escape(obj.error)}</div>"
        )
    url = f"/containerapps/app/{quote(module, safe='')}/{quote(resource, safe='')}"  # noqa: E501
    parts.append(f'<a href="{url}" data-testid="container-app-open">Admin</a>')
    parts.append("</div>")
    return "".join(parts)


def _instance_blurb(
    obj: ContainerAppInstanceResource, module: str, resource: str
) -> str:
    """Render the module page summary for a container app instance."""
    parts = [
        '<div class="container-app-instance-blurb">',
        '<p data-testid="container-app-instance-status">'
        f"Status: {html.escape(obj.status)}</p>",
    ]
    if obj.app_module is not None:
        parts.append(
            '<p data-testid="container-app-instance-app">'
            f"App: {html.escape(obj.app_module)}:{html.escape(obj.app_resource or '')}"  # noqa: E501
            "</p>"
        )
    if obj.error:
        parts.append(
            '<div class="text-red" data-testid="container-app-instance-error">'
            f"{html.escape(obj.error)}</div>"
        )
    url = (
        f"/containerapps/instance/{quote(module, safe='')}"
        f"/{quote(resource, safe='')}"
    )
    parts.append(
        f'<a href="{url}" data-testid="container-app-instance-open">Admin</a>'
    )
    parts.append("</div>")
    return "".join(parts)


app_resource_type = resource_type_from_schema(
    resource_type=APP_RESOURCE_TYPE,
    title="Container App",
    icon="mdi-docker",
    schema=APP_SCHEMA,
    runtime_object_cls=ContainerAppResource,
    default=APP_DEFAULT,
    blurb=_app_blurb,
    after_create=_app_after_create,
    priority=APP_PRIORITY,
)

instance_resource_type = resource_type_from_schema(
    resource_type=INSTANCE_RESOURCE_TYPE,
    title="Container App Instance",
    icon="mdi-docker",
    schema=INSTANCE_SCHEMA,
    runtime_object_cls=ContainerAppInstanceResource,
    default=INSTANCE_DEFAULT,
    blurb=_instance_blurb,
    priority=INSTANCE_PRIORITY,
)
