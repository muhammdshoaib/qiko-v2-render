#!/usr/bin/env python3
from pathlib import Path


STATELESS = "caddy worker qiko-core creator admin"
for name in ("redeploy-preprod.sh", "redeploy-live.sh"):
    source = (Path(__file__).parent / name).read_text()
    migrate = source.index('if [ "$migrated" -ne 1 ]')
    remove = source.index(f"$C rm -sf {STATELESS}")
    recreate = source.index(f"$C up -d --force-recreate qiko-core worker creator admin caddy")
    assert migrate < remove < recreate, f"{name}: stateless removal must follow migration and precede recreation"
    removal_line = source[remove:source.index("\n", remove)]
    assert " db" not in removal_line and " redis" not in removal_line, f"{name}: stateful service in removal"
print("stateless-recreate-contract-pass")
