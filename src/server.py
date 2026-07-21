class ConnectionDefaultsHandler:
    def __init__(self, defaults=None):
        self.defaults = defaults or {}

    def __call__(self, context):
        params = context.llm_params
        for name, value in self.defaults.get(context.connection, {}).items():
            if name == "thinking":
                if value and not params.get("thinking"):
                    params["thinking"] = True
                continue
            if params.get(name) is None:
                params[name] = value

        if params.pop("thinking", False):
            extra = params.get("extra_body") or {}
            if isinstance(extra, dict) and not extra.get("thinking"):
                extra["thinking"] = {"type": "enabled"}
            params["extra_body"] = extra
