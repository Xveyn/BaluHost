"""E2E fixture: routes that exercise storage, core.system_metrics, and denied scope."""


def register(host):
    @host.route("POST", "echo")
    async def echo(request):
        await host.storage.set("last", request["body"])
        value = await host.storage.get("last")
        return {"status": 200, "body": {"stored": value, "user": request["user"]}}

    @host.route("GET", "metrics")
    async def get_metrics(request):
        return {"status": 200, "body": await host.scopes.system_metrics()}

    @host.route("GET", "forbidden")
    async def forbidden(request):
        # 'core.notify' scope is NOT granted — this should be denied by the host
        await host.scopes.notify("x", "y")
        return {"status": 200}
