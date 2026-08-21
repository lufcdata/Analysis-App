#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "Creating MatchLab local environment…"
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

clear
python export_match_json.py

STATUS=$?
echo ""
if [ $STATUS -eq 0 ]; then
  echo "Opening Downloads…"
  open "$HOME/Downloads"
fi

echo ""
read "REPLY?Press Return to close…"
exit $STATUS
