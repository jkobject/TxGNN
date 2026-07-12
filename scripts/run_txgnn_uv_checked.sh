#!/usr/bin/env bash
# Checked, non-installing uv launcher for TxGNN worker preflight and execution.
set -euo pipefail

expected_commit=${TXGNN_EXPECTED_COMMIT:?set TXGNN_EXPECTED_COMMIT to the reviewed checkout SHA}
uv_bin=${TXGNN_UV:-"$HOME/.local/bin/uv"}

case "$uv_bin" in
  /*) ;;
  *) printf 'TXGNN_UV must be an absolute user-local path, got %s\n' "$uv_bin" >&2; exit 64 ;;
esac

if [[ ! -x "$uv_bin" ]]; then
  printf 'checked uv binary is unavailable or not executable: %s\n' "$uv_bin" >&2
  exit 127
fi

actual_commit=$(git rev-parse HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
  printf 'checked checkout mismatch: expected=%s actual=%s\n' "$expected_commit" "$actual_commit" >&2
  exit 65
fi

if command -v sha256sum >/dev/null 2>&1; then
  uv_sha256=$(sha256sum "$uv_bin" | cut -d' ' -f1)
else
  uv_sha256=$(shasum -a 256 "$uv_bin" | cut -d' ' -f1)
fi
printf 'TXGNN_UV_PATH=%s\nTXGNN_UV_SHA256=%s\nTXGNN_CHECKOUT_HEAD=%s\n' "$uv_bin" "$uv_sha256" "$actual_commit"
"$uv_bin" --version
exec "$uv_bin" run "$@"
