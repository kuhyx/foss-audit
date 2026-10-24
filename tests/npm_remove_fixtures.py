"""Lockfiles and helpers shared by the npm-cache remove-command tests."""

from __future__ import annotations

import hashlib

from tests.npm_helpers import pkg_json, tgz

PNPM_LOCK = """---
lockfileVersion: '9.0'

importers:

  .:
    configDependencies: {}
    packageManagerDependencies:
      pnpm:
        specifier: 12.15.0
        version: 12.15.0

packages:

  pnpm@12.15.0:
    resolution: {integrity: sha512-x}

snapshots:

  '@pnpm/exe.linux-x64@12.15.0':
    optional: true

  pnpm@12.15.0:
    optionalDependencies:
      '@pnpm/exe.linux-x64': 12.15.0

---
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      react:
        specifier: 19.0.0
        version: 19.0.0
      '@scope/ui':
        specifier: workspace:*
        version: link:packages/ui
    devDependencies:
      vitest:
        specifier: 3.0.0
        version: 3.0.0(react@19.0.0)

  packages/ui:
    dependencies:
      lodash:
        specifier: 4.17.21
        version: 4.17.21

packages:

  react@19.0.0:
    resolution: {integrity: sha512-r}

snapshots:

  react@19.0.0:
    dependencies:
      scheduler: 0.25.0

  scheduler@0.25.0: {}

  vitest@3.0.0(react@19.0.0):
    dependencies:
      '@vitest/runner': 3.0.0
    peerDependencies:
      ignored: 1.0.0

  '@vitest/runner@3.0.0':
    dependencies:
      p-limit: 5.0.0

  lodash@4.17.21: {}

  unreached@1.0.0: {}
"""

PACKAGE_LOCK = {
    "lockfileVersion": 3,
    "packages": {
        "": {"dependencies": {"express": "^4"}, "devDependencies": {"jest": "^29"}},
        "node_modules/express": {"dependencies": {"body-parser": "1"}},
        "node_modules/body-parser": {"dependencies": {"debug": "2"}, "optionalDependencies": {"ms": "2"}},
        "node_modules/debug": {},
        "node_modules/jest": {},
        "packages/w": {"name": "w", "dependencies": {"chalk": "5"}},
        "node_modules/w": {"resolved": "packages/w", "link": True},
        "node_modules/chalk": {},
    },
}
V1_LOCK = {
    "lockfileVersion": 1,
    "dependencies": {"left-pad": {"version": "1.0.0", "requires": {"debug": "2"}}},
}


def tarball(name: str, deps: dict[str, str] | None = None) -> bytes:
    return tgz(
        [
            (
                "package/package.json",
                pkg_json(name=name, version="1.0.0", license="MIT", dependencies=deps or {}),
            )
        ]
    )


# A single quote inside a single-quoted shell word.
Q = "'\"'\"'"


def bucket(key: str) -> str:
    h = hashlib.sha256(key.encode()).hexdigest()
    return f"~/.npm/_cacache/index-v5/{h[:2]}/{h[2:4]}/{h[4:]}"
