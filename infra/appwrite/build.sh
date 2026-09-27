#!/bin/sh
# Appwrite Python 3.12 (Alpine) build. Native dependencies are packaged in code.
set -eu
role=${1:?Pass api or pipeline}
python3 -m pip install --retries 10 'uv==0.11.19'
uv export --project services/backend --frozen --no-dev --no-emit-project \
  --no-emit-package playwright --no-annotate --no-hashes > /tmp/call-grader-requirements.txt
python3 -m pip install --retries 10 -r /tmp/call-grader-requirements.txt
if [ "$role" = pipeline ]; then
    mkdir -p native
    packages=$(mktemp -d)
    fetched=false
    for attempt in 1 2 3 4; do
        if apk fetch --recursive --no-cache --output "$packages" chromium ffmpeg nodejs; then
            fetched=true
            break
        fi
        sleep 3
    done
    if [ "$fetched" != true ]; then
        echo "Native dependency download failed after four attempts" >&2
        exit 1
    fi
    for package in "$packages"/*.apk; do
        tar -xzf "$package" -C native --exclude='.PKGINFO' --exclude='.SIGN.*' \
          --exclude='.*-install' --exclude='.*-upgrade' --exclude='.*-deinstall'
    done
    rm -rf "$packages"
    python3 infra/appwrite/install_playwright.py
fi
# GitHub/Console deployments must pass the same imports and native checks even
# when the deployment helper is not used.
python3 -c 'from infra.appwrite.common import invocation; from app.main import app; from app.functions.pipeline import dispatch; assert callable(dispatch)'
if [ "$role" = pipeline ]; then
    python3 -c 'from infra.appwrite.common import prepare_native, runtime_check; prepare_native(); print(runtime_check())'
fi
