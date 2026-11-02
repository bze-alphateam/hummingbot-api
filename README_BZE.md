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
- `.github/workflows/lint.yml`, `unit-tests.yml`, `build-image.yml`, `smoke.yml`: our own workflows, one per kind of check. `lint.yml` pins `actions/setup-python` to v5.6.0 because v6.0.0 made the first Lint run fail.
- `utils/beezee_guard.py`: the API never places, cancels or runs executors for `beezee` (see below), and starts no network tasks for a `beezee` account connector.
- `utils/security.py`: a loaded profile of a connector that takes its whole config map (beezee) becomes the connector's configuration, as in the Hummingbot client.
- `models/bot_orchestration.py`: deploy requests default to our bot image.
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
| Unit tests | upstream's `test/` suite inside the built image (the three tests marked `integration` are excluded: they call a separately running API and are not run in CI) |
| Build image | the Dockerfile builds; pushes the tags above on `bze` |
| Smoke | the image runs with `postgres:16` and `emqx:5`; `beezee` is listed, its config map shows `network` and `account_type`, and the connector import plus `ripemd160` work |

## Running BeeZee bots

The API stores a bot's credentials, deploys the bot container from our image and reads its status. The
bot is the only signer of its account: the API never places or cancels orders, or runs executors, for
`beezee` (those routes answer HTTP 400 `beezee trades only inside its bot container`), and it opens no
websocket for a `beezee` account. It only reads balances over REST.

### One profile per bot

Create a credentials profile named after the bot, holding only `beezee`:

```bash
curl -u "$USER:$PASS" -X POST "$API/accounts/add-account?account_name=<bot>"
curl -u "$USER:$PASS" -X POST "$API/accounts/add-credential/<bot>/beezee" \
  -H 'Content-Type: application/json' -d '<body>'
```

Wallet modes use one wallet per bot. Delegated modes use one bot key per granter wallet. The `network`
object is the same in every body; `{}` or leaving it out gives mainnet (`rest.getbze.com`, `rpc.getbze.com`,
`beezee-1`, gas price 0.01). A testnet is picked by its `chain_id`.

```json
"network": {"rest_endpoint": "<rest>", "rpc_endpoint": "<rpc>", "chain_id": "<chain id>",
            "gas_price": "0.01", "gas_adjustment": "1.3"}
```

`account_type`, one of:

```json
{"name": "wallet", "private_key": "<hex>"}
{"name": "wallet_mnemonic", "mnemonic": "<words>", "passphrase": "", "hd_path": "m/44'/118'/0'/0/0"}
{"name": "delegated", "private_key": "<bot hex>", "granter_address": "<bze1...>"}
{"name": "delegated_mnemonic", "mnemonic": "<bot words>", "passphrase": "", "hd_path": "m/44'/118'/0'/0/0",
 "granter_address": "<bze1...>"}
```

`batch_window_ms`, `max_messages_per_tx` and `denom_labels` are optional top-level keys of the same body.
`private_key`, `mnemonic` and `passphrase` are written encrypted to
`bots/credentials/<bot>/connectors/beezee.yml`; the bot container decrypts them with `CONFIG_PASSWORD`.

### Scripts and controllers

The API mounts its shared `bots/scripts` and `bots/controllers` over the image's own, so the BeeZee scripts
(`scripts/beezee_*`) and controllers are not visible in a bot until they are copied there. Copy them from the
bot image you deploy, once per image version:

```bash
id=$(docker create ghcr.io/bze-alphateam/hummingbot:<sha8>)
docker cp "$id":/home/hummingbot/scripts/. bots/scripts/
docker cp "$id":/home/hummingbot/controllers/. bots/controllers/
docker rm "$id"
```

Put the bot's script config (a YAML whose `script_file_name` names the script) in `bots/conf/scripts/`, or
create it through the API's `/scripts` routes, and controller configs in `bots/conf/controllers/`.

### Deploy, status, stop

Always pass `image`. The default is `ghcr.io/bze-alphateam/hummingbot:bze-latest`; pin a `<sha8>` tag for
a real bot. `instance_name` gets a timestamp suffix, and the response returns it as `unique_instance_name`:
use that name below.

```bash
curl -u "$USER:$PASS" -X POST "$API/bot-orchestration/deploy-v2-script" \
  -H 'Content-Type: application/json' -d '{
    "instance_name": "<bot>", "credentials_profile": "<bot>",
    "image": "ghcr.io/bze-alphateam/hummingbot:<sha8>",
    "script": "<beezee script>", "script_config": "<config>.yml", "headless": true}'
```

`deploy-v2-controllers` takes the same fields with `controllers_config` instead of `script`. The container
gets `CONFIG_PASSWORD` and `HEADLESS_MODE=true`, so it logs in, loads the `beezee` connector from the
copied profile and starts the strategy without a prompt. The instance's `conf_client.yml` gets its
`instance_id` and the broker credentials; the MQTT bridge (commands, events, autostart) is on in the profile
template. Without those, status and stop over MQTT do not work.

```bash
curl -u "$USER:$PASS" "$API/bot-orchestration/status"
curl -u "$USER:$PASS" "$API/bot-orchestration/<unique_instance_name>/status"
curl -u "$USER:$PASS" -X POST "$API/bot-orchestration/stop-bot" \
  -H 'Content-Type: application/json' \
  -d '{"bot_name": "<unique_instance_name>", "skip_order_cancellation": false}'
curl -u "$USER:$PASS" -X POST "$API/bot-orchestration/stop-and-archive-bot/<unique_instance_name>?skip_order_cancellation=false"
```

Always send `skip_order_cancellation=false` when stopping, so the bot cancels its own orders. The default
skips the cancellation.

## License

Apache-2.0, as upstream.
