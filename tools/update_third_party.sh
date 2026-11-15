#!/usr/bin/env bash
# Check the vendored upstream repos (third_party/) for new commits and, with --apply, move them forward.
#   tools/update_third_party.sh           show what is new upstream (changes nothing)
#   tools/update_third_party.sh --apply   pull the newest commit of each into third_party/ (then review, test, commit)
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init --depth 1 >/dev/null 2>&1 || git submodule update --init >/dev/null
new=0
for d in third_party/*/; do
  n=$(basename "$d"); cur=$(git -C "$d" rev-parse HEAD); br=$(git config -f .gitmodules "submodule.third_party/$n.branch" || true)
  up=$(git ls-remote "$(git config -f .gitmodules "submodule.third_party/$n.url")" "${br:-HEAD}" | cut -f1 | head -1)
  if [ "$cur" = "$up" ]; then printf '%-14s up to date (%s)\n' "$n" "${cur:0:7}"
  else new=1; printf '%-14s NEW upstream %s (we have %s)\n' "$n" "${up:0:7}" "${cur:0:7}"; fi
done
if [ "${1:-}" = "--apply" ] && [ "$new" = 1 ]; then
  git submodule update --remote --depth 1 || git submodule update --remote
  git status --short third_party; echo "Now read the changes, run the tests, and commit."
fi
exit 0
