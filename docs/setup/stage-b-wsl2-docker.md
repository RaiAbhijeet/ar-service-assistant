# Stage B — WSL2 + Docker setup and troubleshooting runbook

**Target machine:** Dell Precision 7730 · Windows 11 · Quadro P5200 16 GB
**Goal:** the edge stack runs in Docker inside WSL2, reaches Ollama on the Windows host, and is
reachable from the Quest 3S over the LAN.

This file lives in the repo so Claude Code can read it while fixing things. Keep it updated
when you hit something not listed here — the troubleshooting table is a living document.

---

## 0. Two decisions to make before you type anything

### 0.1 Where does the repo live? — **On the Windows drive.**

```
C:\dev\ar-service-assistant          ← from Windows / Unity
/mnt/c/dev/ar-service-assistant      ← the same folder, from WSL
```

**Why not inside WSL (`~/dev/...`)?** Because Unity runs on Windows and must open
`unity/` natively. Unity on a `\\wsl$\...` UNC path is slow and prone to asset-import
weirdness. Unity is the fussier tool, so it wins.

**The cost, stated honestly:** file I/O across the Windows↔WSL boundary (`/mnt/c`) is slow.
`pytest` collection and Docker bind-mount reads will feel sluggish. Mitigations:

- Put Python dependency installation in the **Dockerfile** (`COPY` + `pip install`), not in a
  bind-mounted venv. Rebuild on dependency change, not on every run.
- Use named Docker volumes for `.pytest_cache`, `.mypy_cache`, `.ruff_cache` and Postgres data —
  never bind-mount those.
- Keep `data/` (downloaded manuals, figures) on a **named volume**, not a bind mount.

This tradeoff is worth an ADR. Write it in M0: *"Repo on the Windows filesystem, accepting
9p I/O overhead, because the Unity toolchain requires native Windows paths."*

### 0.2 Networking mode — **turn on mirrored networking.**

Windows 11 22H2+ with WSL ≥ 2.0.0 supports mirrored networking, which makes WSL share the
Windows network stack. With it on, `localhost` inside WSL reaches services on Windows, and the
LAN sees WSL services on the Windows IP. It removes an entire class of "why can't WSL reach
Ollama" problems.

Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
memory=24GB          # you have 64 GB; default is 50% and Docker will happily take it
processors=8
swap=8GB

[experimental]
hostAddressLoopback=true
```

Then, in PowerShell:

```powershell
wsl --shutdown
```

Wait ~10 seconds before restarting Ubuntu, or the change won't take.

> If `networkingMode=mirrored` causes trouble (some VPN clients dislike it), delete that line,
> `wsl --shutdown`, and use the NAT-mode instructions marked **[NAT]** below.

---

## 1. Install, in order

```powershell
# PowerShell as Administrator
wsl --install -d Ubuntu-24.04
wsl --update
wsl --status                 # confirm: default version 2
```

Reboot. Set your Linux username and password on first launch.

Then install **Docker Desktop for Windows** and, in its settings:

- General → **Use the WSL 2 based engine** ✅
- Resources → **WSL Integration** → enable **Ubuntu-24.04** ✅

Reopen the Ubuntu terminal and verify:

```bash
docker version        # both Client and Server must appear
docker compose version
```

Install the basics Ubuntu doesn't ship with:

```bash
sudo apt update && sudo apt install -y build-essential make git curl jq python3-pip
```

---

## 2. Wire WSL → Ollama (on Windows)

Ollama stays **native on Windows**. Containers and WSL reach it over the network.

**On Windows**, set these as *system* environment variables (not just in one terminal) and
restart Ollama from the tray icon:

| Variable | Value |
|---|---|
| `OLLAMA_HOST` | `0.0.0.0:11434` |
| `OLLAMA_KEEP_ALIVE` | `-1` |
| `OLLAMA_FLASH_ATTENTION` | `0` |
| `OLLAMA_MAX_LOADED_MODELS` | `1` |

Open the firewall for it:

```powershell
New-NetFirewallRule -DisplayName "Ollama LAN" -Direction Inbound -LocalPort 11434 `
  -Protocol TCP -Action Allow -Profile Private
```

**Verify from inside WSL:**

```bash
# mirrored networking:
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# [NAT] fallback if mirrored is off:
WIN_HOST=$(ip route show default | awk '{print $3}')
curl -s http://$WIN_HOST:11434/api/tags | jq '.models[].name'
```

You should see `qwen3-vl:8b` and `bge-m3`. If this fails, stop and fix it — everything
downstream depends on it.

**From inside a container**, the address is `http://host.docker.internal:11434`. Docker Desktop
provides this name; the compose file also sets `extra_hosts: ["host.docker.internal:host-gateway"]`
so it works if you ever move to Docker Engine.

---

## 3. Wire the Quest → your machine

```powershell
ipconfig     # take the IPv4 of the Wi-Fi adapter, e.g. 192.168.1.50
```

Put it in `.env` as `ARSA_HOST_IP`. Then:

```powershell
# Make sure the Wi-Fi network profile is Private, not Public
Get-NetConnectionProfile
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private

New-NetFirewallRule -DisplayName "ARSA API" -Direction Inbound -LocalPort 8000 `
  -Protocol TCP -Action Allow -Profile Private
```

**Test before you have an API.** In WSL:

```bash
python3 -m http.server 8000
```

Put the headset on, open the Quest browser, go to `http://<ARSA_HOST_IP>:8000`. If you see a
directory listing, networking is done. Do this now — debugging this later, while also debugging
Unity, is genuinely miserable.

---

## 4. adb: it must run on Windows, not in WSL

USB devices are not visible to WSL by default. Two options — **use option B.**

**Option A — call the Windows binary from WSL.** Windows executables are callable from WSL:

```bash
adb.exe devices          # note the .exe
```

Works, but paths get confusing in scripts.

**Option B (recommended) — adb over Wi-Fi.** No cable, no interop weirdness, and it survives
you walking around with the headset on:

```powershell
# once, with the Quest connected by USB, from PowerShell:
adb tcpip 5555
# then unplug and, from anywhere on the LAN:
adb connect <quest-ip>:5555
adb devices
```

Find the Quest's IP in the headset under Settings → Wi-Fi → your network.

**Makefile note:** the `install` and `perf` targets call `adb`. On WSL, either alias
`adb=adb.exe` in your `~/.bashrc`, or install `adb` in Ubuntu (`sudo apt install adb`) and use
Option B, which works from the Linux binary because it's a network connection.

---

## 5. `make doctor` — run this before asking anyone anything

Create `tools/doctor.sh`, make it executable, and run it whenever something is off. It answers
about 80 % of "why doesn't it work".

```bash
#!/usr/bin/env bash
# tools/doctor.sh — environment diagnostics. Run from the repo root inside WSL.
set -uo pipefail
ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad(){ printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }
FAIL=0

echo "== WSL / OS =="
grep -qi microsoft /proc/version && ok "running inside WSL" || bad "not WSL"
[ -d /mnt/c ] && ok "/mnt/c mounted" || bad "/mnt/c missing"

echo "== repo location =="
case "$PWD" in
  /mnt/c/*) ok "repo on Windows drive ($PWD) — expected" ;;
  *) bad "repo is at $PWD, not on /mnt/c — Unity will not see it natively" ;;
esac

echo "== tooling =="
for c in docker git make python3 curl jq; do
  command -v $c >/dev/null && ok "$c present" || bad "$c missing"
done
docker version >/dev/null 2>&1 && ok "docker daemon reachable" \
  || bad "docker daemon unreachable — enable WSL integration in Docker Desktop"

echo "== ollama =="
HOSTS=("http://localhost:11434" "http://$(ip route show default | awk '{print $3}'):11434")
FOUND=""
for h in "${HOSTS[@]}"; do
  if curl -fsS --max-time 3 "$h/api/tags" >/dev/null 2>&1; then FOUND="$h"; break; fi
done
if [ -n "$FOUND" ]; then
  ok "ollama reachable at $FOUND"
  curl -fsS "$FOUND/api/tags" | jq -r '.models[].name' | sed 's/^/    - /'
  curl -fsS "$FOUND/api/tags" | jq -e '.models[].name|select(startswith("qwen3-vl"))' >/dev/null \
    && ok "qwen3-vl present" || bad "qwen3-vl not pulled"
  curl -fsS "$FOUND/api/tags" | jq -e '.models[].name|select(startswith("bge-m3"))' >/dev/null \
    && ok "bge-m3 present" || bad "bge-m3 not pulled"
else
  bad "ollama unreachable — check OLLAMA_HOST=0.0.0.0:11434 and the firewall rule"
fi

echo "== env =="
[ -f .env ] && ok ".env exists" || bad ".env missing (cp .env.example .env)"
if [ -f .env ]; then
  IP=$(grep -E '^ARSA_HOST_IP=' .env | cut -d= -f2)
  [ -n "$IP" ] && [ "$IP" != "192.168.1.50" ] && ok "ARSA_HOST_IP set to $IP" \
    || bad "ARSA_HOST_IP still the placeholder — run ipconfig on Windows"
fi

echo "== adb =="
if command -v adb >/dev/null || command -v adb.exe >/dev/null; then
  ADB=$(command -v adb || command -v adb.exe)
  ok "adb found ($ADB)"
  "$ADB" devices | grep -qE 'device$' && ok "a device is attached" \
    || bad "no device — run: adb connect <quest-ip>:5555"
else
  bad "adb missing"
fi

echo
[ "$FAIL" -eq 0 ] && echo "All checks passed." || echo "Some checks failed — see ✗ above."
exit $FAIL
```

Add to the Makefile:

```make
doctor: ## Diagnose the local environment
	bash tools/doctor.sh
```

---

## 6. Troubleshooting table

| Symptom | Cause | Fix |
|---|---|---|
| `wsl --install` fails, or WSL2 won't start | Virtualization disabled in BIOS | Reboot, **F2** into Dell BIOS setup → *Virtualization Support* → enable **VT-x** and **VT-d**. The 7730 ships with these off in some configurations. |
| `WslRegisterDistribution failed with error: 0x800701bc` | Outdated WSL kernel | `wsl --update`, then `wsl --shutdown` |
| `docker: command not found` inside Ubuntu | WSL integration off | Docker Desktop → Settings → Resources → WSL Integration → enable Ubuntu-24.04 → Apply & Restart |
| `Cannot connect to the Docker daemon` | Docker Desktop not running, or integration applied but shell not restarted | Start Docker Desktop, then open a new Ubuntu terminal |
| `curl: (7) Failed to connect to ...:11434` from WSL | `OLLAMA_HOST` still `127.0.0.1`, or firewall | Set `OLLAMA_HOST=0.0.0.0:11434` as a **system** variable, restart Ollama from the tray, add the firewall rule from §2 |
| Ollama reachable from WSL but not from a container | Missing host mapping | `extra_hosts: ["host.docker.internal:host-gateway"]` in the api service (already in the compose file) |
| Quest browser can't reach `http://<ip>:8000` | Wi-Fi profile is *Public*, or no inbound rule | `Set-NetConnectionProfile ... -NetworkCategory Private` plus the port-8000 rule (§3) |
| Quest and laptop on different subnets | Guest network / band separation on the router | Put both on the same 5 GHz SSID; disable client isolation on the router |
| `docker compose up` extremely slow, or pytest takes minutes | Bind-mounting caches across `/mnt/c` | Move `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `data/` and Postgres data to **named volumes** |
| WSL eats all 64 GB of RAM | No `.wslconfig` limit | Add `memory=24GB` to `.wslconfig`, `wsl --shutdown` |
| Disk filling up, `ext4.vhdx` huge | WSL disk doesn't auto-shrink | `wsl --shutdown`, then `Optimize-VHD` in PowerShell, or `docker system prune -af --volumes` first |
| `adb devices` empty in WSL | USB not passed through to WSL | Use `adb connect <quest-ip>:5555` (§4) |
| Line endings mangled / CI fails on files that work locally | Windows CRLF | Already handled by `.gitattributes` (`* text=auto eol=lf`). Verify with `git config core.autocrlf` → should be `input` or unset. |
| `make: command not found` | Ubuntu minimal install | `sudo apt install build-essential` |
| Unity can't find the project after moving it | Repo not on `/mnt/c` | See §0.1 — the repo must live on the Windows drive |
| Model reloads on every request, latency spikes 20–40 s | `OLLAMA_KEEP_ALIVE` unset | Set it to `-1`, restart Ollama |
| `ollama ps` shows CPU, not 100 % GPU | Model too large for 16 GB with the chosen context, or driver < 550 | Drop to `qwen3-vl:4b`, reduce context, or update the NVIDIA driver |

---

## 7. Definition of done for Stage B

- [ ] `bash tools/doctor.sh` exits 0
- [ ] `curl http://localhost:11434/api/tags` from WSL lists `qwen3-vl:8b` and `bge-m3`
- [ ] Quest browser loads `http://<ARSA_HOST_IP>:8000` (any server)
- [ ] `adb devices` from WSL shows the Quest over TCP
- [ ] `docker compose -f server/docker-compose.yml config` parses without error
- [ ] `.wslconfig` caps memory; `wsl --shutdown` performed after editing it

When all six are true, start **M0.1** in the implementation guide. Not before.
