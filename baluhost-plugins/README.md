# baluhost-plugins (DEPRECATED)

> **⚠️ Deprecated — kept for history only.**
>
> This directory was an early in-repo prototype of the BaluHost plugin
> marketplace. The live marketplace now lives in its own repository at
> [Xveyn/BaluHost-Plugin-Market](https://github.com/Xveyn/BaluHost-Plugin-Market),
> which is what the backend fetches via `plugins_marketplace_index_url`.
>
> Do not add new plugins or edit build tooling here — use the external repo
> instead. This folder is frozen and may be removed in a future cleanup.

Community plugin registry for [BaluHost](https://github.com/Xveyn/Baluhost). Plugins live in
`plugins/<name>/` with a static `plugin.json` manifest. A CI job walks the
tree, packages each plugin into a `.bhplugin` zip, and publishes an
`index.json` that BaluHost reads at runtime.

## Layout

```
baluhost-plugins/
├── plugins/               # plugin sources, one subdirectory per plugin
│   └── <name>/
│       ├── plugin.json    # static manifest — single source of truth
│       ├── __init__.py    # PluginBase subclass
│       ├── ui/bundle.js   # optional — frontend bundle
│       └── requirements.txt  # optional — pinned pure-Python deps
├── scripts/
│   └── build_index.py     # builds dist/index.json + <name>-<ver>.bhplugin
├── tests/
│   └── test_build_index.py
└── .github/workflows/
    └── publish.yml        # CI: build + publish dist/ to GitHub Pages
```

## Adding a plugin

1. Create `plugins/my_plugin/`.
2. Drop a `plugin.json` that matches the schema validated by
   [`backend/app/plugins/manifest.py`](../backend/app/plugins/manifest.py)
   (`manifest_version: 1`, name, version, display_name, description,
   author, plus optional category, permissions, `python_requirements`).
3. Add your Python entrypoint (`__init__.py` by default) and any
   supporting files. Keep everything pure-Python — the marketplace
   installer rejects C extensions.
4. Open a pull request. CI runs `scripts/build_index.py`, validates
   every manifest, and refuses to merge on schema errors.

## Building the index locally

```bash
cd baluhost-plugins
python scripts/build_index.py --source plugins --dist dist
```

The script emits:

- `dist/index.json` — the marketplace index that BaluHost fetches
- `dist/<name>-<version>.bhplugin` — one zip artifact per plugin, with
  SHA-256 checksums embedded in the index

A plugin URL in the index is rewritten at CI time via the
`--base-url` flag so the same build script works for local testing
(`file://`) and for the published GitHub Pages site.

## Versioning

v1 publishes a single version per plugin — the current checkout. Older
versions are recovered from git history by re-running the build on a
tagged commit. Multi-version coexistence in a single index is a v2
concern tracked in the spec.
