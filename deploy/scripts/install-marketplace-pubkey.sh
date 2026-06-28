#!/bin/bash
# Idempotently set PLUGINS_MARKETPLACE_PUBLIC_KEYS in .env.production from a
# server-side base64 public-key file (one key per line, '#' comments allowed).
# Public material only — no secret handling. Run as root at setup / on key
# rotation. Validates each key is base64 of exactly 32 bytes before writing,
# so a bad key never silently fail-closes the marketplace.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/baluhost}"
ENV_FILE="$INSTALL_DIR/.env.production"
PUBKEY_FILE="${MARKETPLACE_PUBKEY_FILE:-/etc/baluhost/marketplace-pubkey.b64}"
KEY_VAR="PLUGINS_MARKETPLACE_PUBLIC_KEYS"

err() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]]    || err "$ENV_FILE not found"
[[ -f "$PUBKEY_FILE" ]] || err "public key file $PUBKEY_FILE not found"

# Collect non-empty, non-comment keys; validate each decodes to 32 bytes.
keys=()
while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"   # ltrim
    line="${line%"${line##*[![:space:]]}"}"     # rtrim
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    nbytes=$(printf '%s' "$line" | base64 -d 2>/dev/null | wc -c) \
        || err "key is not valid base64: $line"
    [[ "$nbytes" -eq 32 ]] \
        || err "key is not a 32-byte ed25519 public key (got $nbytes bytes): $line"
    keys+=("$line")
done < "$PUBKEY_FILE"

[[ "${#keys[@]}" -gt 0 ]] || err "no public keys found in $PUBKEY_FILE"

# Build a comma-separated value (base64 contains no comma → unambiguous).
# Plain CSV with no quotes/brackets is consumed verbatim by bash `source`
# (ci-deploy), systemd EnvironmentFile, and python-dotenv — no quote-stripping
# pitfalls. The Settings validator (parse_marketplace_public_keys) comma-splits.
csv=""
for i in "${!keys[@]}"; do
    [[ "$i" -gt 0 ]] && csv+=","
    csv+="${keys[$i]}"
done
new_line="$KEY_VAR=$csv"

# Idempotent set: no-op if identical, replace if present, append if absent.
# Write through the existing file (truncate+rewrite) to preserve owner/mode.
if existing=$(sed -n "s/^${KEY_VAR}=.*/&/p" "$ENV_FILE") && [[ -n "$existing" ]]; then
    if [[ "$existing" == "$new_line" ]]; then
        echo "$KEY_VAR already up to date in $ENV_FILE"
        exit 0
    fi
    tmp=$(mktemp)
    sed "/^${KEY_VAR}=/d" "$ENV_FILE" > "$tmp"
    printf '%s\n' "$new_line" >> "$tmp"
    cat "$tmp" > "$ENV_FILE"
    rm -f "$tmp"
    echo "Updated $KEY_VAR in $ENV_FILE"
else
    printf '%s\n' "$new_line" >> "$ENV_FILE"
    echo "Appended $KEY_VAR to $ENV_FILE"
fi
