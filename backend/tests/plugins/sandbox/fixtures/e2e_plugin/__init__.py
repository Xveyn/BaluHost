"""E2E fixture: a route that reads+writes storage and returns it."""


def register(host):
    @host.route("POST", "echo")
    async def echo(request):
        await host.storage.set("last", request["body"])
        value = await host.storage.get("last")
        return {"status": 200, "body": {"stored": value, "user": request["user"]}}
