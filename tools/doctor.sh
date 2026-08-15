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
  /mnt/[a-z]/*) ok "repo on Windows drive ($PWD) — expected" ;;
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
