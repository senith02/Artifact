# Exact-time re-dispatch from your own server (optional; DL-038 §11)

**Why this exists.** GitHub's `schedule` trigger is best-effort. On 2026-10-21/22 an hourly schedule
ran only 3 times in 12 hours, so a build deferred to 02:00 UTC was not re-run until someone clicked
**Run workflow** at 03:11.

`carbon_tick.py` fixes that from any always-on Linux machine:

1. It reads the open `carbon-deferral` issues (read-only) and their due times. That's one API call,
   and nothing runs on GitHub Actions.
2. It **sleeps until the earliest due time**, and re-checks every 5 minutes for new deferrals.
3. At the due time it starts `carbon-dispatch.yml` **once**. GitHub starts a manually triggered
   workflow within about a minute, and the dispatcher then starts the build at the deferred commit
   and closes the issue.

**Guarantees:**
- The server only ever says "start the dispatcher now". All checking happens in the dispatcher on
  GitHub.
- If an issue is still open 20 minutes after a trigger, the server triggers again, so a deferral is
  never dropped.
- If the server is down, the dispatcher's backup schedule still re-runs the build, only later.

It uses only the Python standard library. Nothing else is installed, and no virtualenv is needed.

## 1. Create a token (on github.com)

Go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new
token**:

- **Repository access:** *Only select repositories* → the repository with the deferrals (e.g.
  `carbon-advisor-demo`).
- **Repository permissions:**
  - **Actions: Read and write**, to start the dispatcher;
  - **Issues: Read-only**, to read the due times.

  Leave everything else at *No access*. *Metadata: Read-only* is added automatically.
- **Expiration:** e.g. 90 days. Put a reminder in your calendar to renew it.

Copy the token. You will paste it once in step 3.

## 2. Copy the script to the server (Ubuntu, any architecture)

```bash
python3 --version              # Ubuntu ships Python 3; if missing: sudo apt update && sudo apt install -y python3
sudo mkdir -p /opt/carbon-tick
sudo curl -fsSL -o /opt/carbon-tick/carbon_tick.py \
  https://raw.githubusercontent.com/senith02/Artifact/main/Research_Artifact/code/github-action/examples/vps-trigger/carbon_tick.py
sudo chmod 644 /opt/carbon-tick/carbon_tick.py
```

(For a fixed version, replace `main` in the URL with a commit SHA.)

## 3. Store the token where only root can read it

```bash
sudo install -m 600 /dev/null /etc/carbon-tick.env
sudo nano /etc/carbon-tick.env        # add one line:  GITHUB_TOKEN=github_pat_...
```

## 4. Test it once, without triggering anything

```bash
sudo bash -c 'set -a; . /etc/carbon-tick.env; python3 /opt/carbon-tick/carbon_tick.py \
  --repo senith02/carbon-advisor-demo --once --dry-run'
```

You should see something like this:

```
2026-10-22 03:33:21 UTC  carbon-tick watching senith02/carbon-advisor-demo (dispatcher carbon-dispatch.yml on main)
2026-10-22 03:33:22 UTC  0 open deferral(s); sleeping until 03:38:21 UTC
```

`HTTP 401` means the token is wrong. `HTTP 403` or `404` means it lacks a permission or the
repository.

## 5. Run it for good, as a service

```bash
sudo curl -fsSL -o /etc/systemd/system/carbon-tick.service \
  https://raw.githubusercontent.com/senith02/Artifact/main/Research_Artifact/code/github-action/examples/vps-trigger/carbon-tick.service
# Edit --repo in that file if your repository is not senith02/carbon-advisor-demo.
sudo systemctl daemon-reload
sudo systemctl enable --now carbon-tick
systemctl status carbon-tick --no-pager     # should say: active (running)
journalctl -u carbon-tick -f                # live log; Ctrl+C to stop watching
```

The service:
- starts at boot and restarts itself after a crash;
- runs as a throwaway unprivileged user (`DynamicUser=yes`) with a read-only view of the system.

When a deferral comes due, the log shows:

```
... due: issue(s) #4 -> starting carbon-dispatch.yml
```

A minute later, **Actions → ci** shows the `workflow_dispatch` build.

## Everyday commands

| To… | Run |
| :-- | :-- |
| see what it is doing | `journalctl -u carbon-tick -n 50 --no-pager` |
| restart it (e.g. after renewing the token) | `sudo systemctl restart carbon-tick` |
| stop it | `sudo systemctl disable --now carbon-tick` |
| update the script | repeat the `curl` in step 2, then restart |

## Options

| Option | Default | Meaning |
| :-- | :-- | :-- |
| `--repo` | (required) | `owner/name` |
| `--workflow` | `carbon-dispatch.yml` | the dispatcher workflow file |
| `--ref` | `main` | the branch the dispatcher runs on |
| `--poll` | `300` | re-check for new deferrals every N seconds |
| `--retry` | `1200` | trigger again if a due issue is still open after N seconds |
| `--once` | off | check once and exit |
| `--dry-run` | off | log what would happen; trigger nothing |

**No server?** A free hosted cron service (for example cron-job.org) can make the same API call at
minute 0 of every hour:

```
POST https://api.github.com/repos/OWNER/REPO/actions/workflows/carbon-dispatch.yml/dispatches
with header  Authorization: Bearer <token>
and body     {"ref":"main"}
```

Deferral times are always on the hour, so that is punctual too. It just runs the dispatcher every
hour instead of only when needed.
