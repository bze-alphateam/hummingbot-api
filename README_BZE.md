# hummingbot-api (BZE fork)

Fork of [hummingbot/hummingbot-api](https://github.com/hummingbot/hummingbot-api), the
official Hummingbot API. The upstream image installs `hummingbot` from PyPI, which has no
BeeZee connector. This fork installs it from
[bze-alphateam/hummingbot](https://github.com/bze-alphateam/hummingbot) instead, so the API
can list `beezee`, store and validate its credentials and read balances. Nothing else in
the API is changed.

## Branches

- `main` mirrors upstream `main` and is never committed to.
- `bze` is the default branch: upstream plus our few changes. All work goes through PRs into `bze`.

## What differs from upstream

- `environment.yml`: `hummingbot` is installed with pip from our fork, pinned to a commit.
- `Dockerfile` (builder stage): adds `git`, needed for that install. The compiler packages were already there; they build the Cython extensions.
- `.github/workflows/docker_buildx_workflow.yml`: only runs on the upstream repository (it pushes to Docker Hub with upstream secrets).
- `.github/workflows/`: four workflows of our own, one per kind of check: `lint.yml`, `unit-tests.yml`, `build-image.yml`, `smoke.yml`.
- This file.

## Install method

pip straight from git: the builder stage runs `conda env create`, whose pip section builds
`hummingbot` from the pinned commit of our fork (`setup.py` runs `cythonize`). It keeps the
Dockerfile identical to upstream apart from `git`.

Fallback, if that build ever fails or takes more than about 30 minutes in CI: copy the built
`hummingbot` package (site-packages entry plus the compiled `.so` files) from
`ghcr.io/bze-alphateam/hummingbot:<sha8>` into the API's conda env in a multi-stage build,
and update this section.

## Bump the pinned hummingbot commit

1. Take the new commit sha of the `bze` branch of `bze-alphateam/hummingbot`.
2. Replace the sha in the `hummingbot @ git+https://...@<sha>` line of `environment.yml`.
3. Open a PR into `bze`. The smoke workflow shows the connector still loads.

## Sync upstream

1. Fast-forward `main` from upstream (`gh repo sync bze-alphateam/hummingbot-api --branch main`).
2. Merge `main` into a topic branch off `bze` and open a PR into `bze`.
3. Keep the diff against upstream as small as listed above, so this merge stays easy.

## Images

Pushed to GHCR on every push to `bze`:

- `ghcr.io/bze-alphateam/hummingbot-api:<sha8>` (first 8 characters of the commit)
- `ghcr.io/bze-alphateam/hummingbot-api:bze-latest`

Pull requests build the image without pushing it.

## CI

| Workflow | What it checks |
| --- | --- |
| Lint | upstream's pre-commit hooks on the changed files |
| Unit tests | upstream's `test/` suite inside the built image (tests marked `integration` excluded) |
| Build image | the Dockerfile builds; pushes the tags above on `bze` |
| Smoke | the image runs with `postgres:16` and `emqx:5`; `beezee` is listed, its config map shows `network` and `account_type`, and the connector import plus `ripemd160` work |

## License

Apache-2.0, as upstream.
