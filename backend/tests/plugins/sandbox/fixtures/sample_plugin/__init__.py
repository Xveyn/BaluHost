# Fixture plugin for Track B Phase 3 e2e tests.
# Uses ONLY the SDK (host.route, host.storage, host.scopes) — no host imports.


def register(host):
    @host.route("POST", "/save")
    async def save(request):
        await host.storage.set("note", request["body"])
        return {"status": 200, "body": {"saved": True}}

    @host.route("GET", "/load")
    async def load(request):
        return {"status": 200, "body": {"note": await host.storage.get("note")}}

    @host.route("GET", "/metrics")
    async def metrics(request):
        return {"status": 200, "body": await host.scopes.system_metrics()}

    @host.route("GET", "/forbidden")
    async def forbidden(request):
        # 'core.notify' scope is NOT granted in the denied-path test
        await host.scopes.notify("t", "m")
        return {"status": 200}
