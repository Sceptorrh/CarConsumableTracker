# Deploying on unRAID

How it fits together:

```
 you / Claude ──push──► GitHub (public repo)
                          │  GitHub Actions: tests → Docker image
                          ▼
                    ghcr.io/sceptorrh/carconsumabletracker:latest   (public image)
                          ▲  pulled every hour (only this container)
 unRAID ──────────────────┤
   ├─ car-consumable-tracker          web UI + API on :8000, data in appdata
   ├─ car-consumable-tracker-updater  Watchtower, scoped to the container above
   └─ VM: Home Assistant  ──REST──► :8000/api/v1/status   ◄──webhook── events
```

Nothing on your server is reachable from the outside; unRAID only pulls. The repository and
the image are public, so no GitHub account or token is needed on unRAID.

## 1. GitHub (already done)

- `main` is the default branch. Images are only published from `main` (and version tags).
- The *Actions* tab → workflow **CI** shows every build; tests run before an image is built.
- The image is public: repo page → *Packages* → **carconsumabletracker** → *Package settings*
  → visibility **Public**. Check it from the unRAID terminal – this must work without logging in:
  ```bash
  docker pull ghcr.io/sceptorrh/carconsumabletracker:latest
  ```
  `denied` / `unauthorized` means the package is still private (see
  [Private image](#private-image-optional) at the end).

## 2. unRAID

1. **Install the Compose plugin:** *Apps* → search **Docker Compose Manager** → install.
2. **Create the stack:** *Docker* tab → bottom section **Compose** → **Add New Stack** →
   name `car-consumable-tracker`.
   - ⚙ → **Edit Stack → Compose File**: paste [`docker-compose.yml`](../docker-compose.yml).
   - ⚙ → **Edit Stack → Env File**: paste [`.env.example`](../.env.example) and fill in:
     - `CCT_API_TOKEN` – any long random string (`openssl rand -hex 24` in the terminal)
     - `CCT_HA_WEBHOOK_URL` – `http://<HA-VM-IP>:8123/api/webhook/car_consumable_tracker`
     - `CCT_PORT` – change if 8000 is already used on your server
     - leave `GHCR_USER` / `GHCR_TOKEN` empty (only for a private image)
3. **Compose Up.** Open `http://<UNRAID-IP>:8000`.

Data lives in `/mnt/user/appdata/car-consumable-tracker/cct.db` – one SQLite file. Include
it in your appdata backup (e.g. the *Appdata Backup* plugin).

## 3. Home Assistant (VM)

1. Copy [`homeassistant/packages/car_consumable_tracker.yaml`](../homeassistant/packages/car_consumable_tracker.yaml)
   to `/config/packages/` and replace `UNRAID-IP:8000` and vehicle id `1` / "golf".
2. In `secrets.yaml`: `cct_auth: "Bearer <CCT_API_TOKEN>"`.
3. Restart Home Assistant.

The HA VM must be on your LAN (network source **br0** in the VM settings, which is the
default for most HA VM setups). With the NAT network `virbr0`, the app can't reach HA's
webhook.

## Updating

Automatic: merge to `main` → GitHub builds `latest` (≈3 min) → the updater pulls it at its
next check (default every hour, `CCT_UPDATE_INTERVAL`) and recreates the container. Database
migrations run on start-up. The data folder is untouched.

Manually, instead or in between: *Docker* tab → Compose stack → **Update Stack**.

**Pin or roll back:** tag a release in GitHub (`v1.2.0`) to get image tags `1.2.0` and `1.2`.
Set `CCT_TAG=1.2.0` in the env file and Compose Up; the updater then stays on that tag.
Every build also has a `sha-<commit>` tag.

> Rolling back to a version *older than a database migration* is not supported automatically –
> restore the `cct.db` backup from before the update in that case.

## Security notes

- The **web UI has no login**. Keep it on your LAN; don't port-forward 8000. For access from
  outside, use a VPN (Tailscale/WireGuard) or a reverse proxy with authentication.
- The API (`/api/*`, what Home Assistant uses) requires `CCT_API_TOKEN` when it's set.
- The updater needs the Docker socket (like every auto-updater). Its scope limits it to the
  `car-consumable-tracker` container; other containers and VMs are never touched. Don't want
  that? Remove the `cct-updater` service and use **Update Stack** manually.

## Private image (optional)

Only needed if you ever make the repository or package private again.

1. GitHub → *Settings → Developer settings → Personal access tokens → Tokens (classic)* →
   **Generate new token (classic)** with **only `read:packages`**
   ([shortcut](https://github.com/settings/tokens/new?scopes=read:packages&description=unraid-car-consumable-tracker)).
   Fine-grained tokens can't read container images.
2. Put your GitHub username and the token in `GHCR_USER` / `GHCR_TOKEN` (used by the updater).
3. unRAID terminal: `docker login ghcr.io -u <github-username>`, password = the token.
   unRAID keeps `/root` in RAM, so this login is forgotten after a reboot; the running container
   and the updater are unaffected, only a manual pull needs a fresh login.
4. If the token expires, the updater logs pull errors and updates stop until you renew it.

## Alternative: plain unRAID template (no Compose plugin)

[`deploy/unraid/car-consumable-tracker.xml`](../deploy/unraid/car-consumable-tracker.xml) is a
regular unRAID Docker template. Copy it to
`/boot/config/plugins/dockerMan/templates-user/my-car-consumable-tracker.xml`, then
*Docker → Add Container → Template*. Updates then come from unRAID's own "check for updates"
(or the *CA Auto Update Applications* plugin) instead of Watchtower.
