#!/bin/sh
# One-time setup. Run from this folder:  sh setup.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

if ! python3 -m pip install -r requirements.txt; then
  if python3 -c "import PIL" >/dev/null 2>&1; then
    echo "Note: could not run pip, but Pillow is already installed, so that is fine."
  else
    echo "Could not install Pillow. Try:  python3 -m pip install Pillow"
    exit 1
  fi
fi

# turn on the safety check before every push, if this folder is a git repo of its own
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  git config core.hooksPath .githooks
  echo "Safety check switched on (runs before every push)."
fi
chmod +x .githooks/pre-push 2>/dev/null || true

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Made .env from .env.example (it is private)."
fi
echo "Setup done. Next: follow README.md step 2."
