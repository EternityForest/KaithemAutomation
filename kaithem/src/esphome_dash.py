def start_web_server():
    try:
        from esphome.dashboard import dashboard
        import os
        from . import directories, messagebus

        p = os.path.join(directories.vardir, os.path.expanduser("~/esphome"))
        os.makedirs(p, exist_ok=True)
        dashboard.settings.absolute_config_dir = dashboard.settings.config_dir = p
        os.environ["ESPHOME_DASHBOARD_RELATIVE_URL"] = "/esphome/"
        dashboard.mkdir_p(dashboard.settings.rel_path(".esphome"))

        app = dashboard.make_app()
        status_thread = dashboard.MDNSStatusThread(daemon=True)
        status_thread.start()
    except Exception:
        messagebus.post_message(
            "/system/notifications/errors",
            "Failed to initialize ESPHome server",
        )
        return None

    return app
