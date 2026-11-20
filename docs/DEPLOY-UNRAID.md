# Deploying on unRAID

How it fits together:

```
 you / Claude ──push──► GitHub (private repo)
                          │  GitHub Actions: tests → Docker image
                          ▼
                    ghcr.io/sceptorrh/carconsumabletracker:latest
                          ▲  pulled every hour (only this container)
 unRAID ──────────────────┤
   ├─ car-consumable-tracker          web UI + API on :8000, data in appdata
   ├─ car-consumable-tracker-updater  Watchtower, scoped to the container above
   └─ VM: Home Assistant  ──REST──► :8000/api/v1/status   ◄──webhook── events
```

Nothing on your server is reachable from the outside; unRAID only pulls.

## 1. One-time GitHub setup

1. **Create `main`.** Images are only published from the `main` branch (and from version
   tags). Merge the work branch into `main` (or create `main` from it), and set `main` as the
   default branch: *Settings → General → Default branch*.
2. **Watch the first build.** *Actions* tab → workflow **CI**. Tests run first, then the image
   is built and published. Afterwards it shows up under *Packages* on the repo page.
3. **Give unRAID read access to the image.** The repo is private, so the image is too. Pick one:
   - **Token (keeps it private):** GitHub → *Settings → Developer settings → Personal access
     tokens → Tokens (classic)* → new token with **only `read:packages`**, no expiry or a long
     one. (Fine-grained tokens can't read container packages.)
   - **Public image:** package page → *Package settings → Change visibility → Public*. The
     code stays private in the repo, but anyone could pull (and inspect) the image.

## 2. unRAID

1. **Install the Compose plugin:** *Apps* → search **Docker Compose Manager** → install.
2. **Log in to GitHub's registry** (only for the token option). unRAID *Terminal*:
   ```bash
   docker login ghcr.io -u <your-github-username>
   # paste the read:packages token as password
   ```
   unRAID keeps `/root` in RAM, so this login is forgotten after a reboot. That's fine: the
   running container is unaffected and the updater uses its own credentials (below). Only
   repeat it if you ever pull by hand after a reboot.
3. **Create the stack:** *Docker* tab → bottom section **Compose** → **Add New Stack** →
   name `car-consumable-tracker`.
   - ⚙ → **Edit Stack → Compose File**: paste [`docker-compose.yml`](../docker-compose.yml).
   - ⚙ → **Edit Stack → Env File**: paste [`.env.example`](../.env.example) and fill in:
     - `CCT_API_TOKEN` – any long random string (`openssl rand -hex 24` in the terminal)
     - `CCT_HA_WEBHOOK_URL` – `http://<HA-VM-IP>:8123/api/webhook/car_consumable_tracker`
     - `GHCR_USER` / `GHCR_TOKEN` – your GitHub username and the `read:packages` token
       (leave empty if you made the image public)
     - `CCT_PORT` – change if 8000 is already used on your server
4. **Compose Up.** Open `http://<UNRAID-IP>:8000`.

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

## Alternative: plain unRAID template (no Compose plugin)

[`deploy/unraid/car-consumable-tracker.xml`](../deploy/unraid/car-consumable-tracker.xml) is a
regular unRAID Docker template. Copy it to
`/boot/config/plugins/dockerMan/templates-user/my-car-consumable-tracker.xml`, then
*Docker → Add Container → Template*. Updates then come from unRAID's own "check for updates"
(or the *CA Auto Update Applications* plugin) instead of Watchtower.
