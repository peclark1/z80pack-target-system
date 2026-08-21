#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
UPSTREAM_DIR="$ROOT/build/z80pack-upstream"
UPSTREAM_URL="https://github.com/udo-munk/z80pack.git"
UPSTREAM_COMMIT="91fd28eb04e675c2127df88ed3f40675e15282e2"

mkdir -p "$ROOT/build"

if [[ ! -d "$UPSTREAM_DIR/.git" ]]; then
    git clone "$UPSTREAM_URL" "$UPSTREAM_DIR"
fi

git -C "$UPSTREAM_DIR" fetch --quiet origin "$UPSTREAM_COMMIT"
git -C "$UPSTREAM_DIR" checkout --quiet --detach "$UPSTREAM_COMMIT"

actual=$(git -C "$UPSTREAM_DIR" rev-parse HEAD)
if [[ "$actual" != "$UPSTREAM_COMMIT" ]]; then
    echo "error: z80pack checkout is $actual, expected $UPSTREAM_COMMIT" >&2
    exit 1
fi

echo "z80pack upstream ready at $UPSTREAM_DIR"
echo "revision: $actual"
