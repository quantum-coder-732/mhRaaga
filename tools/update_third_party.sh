#!/usr/bin/env bash
# The upstream repos are copied into third_party/ (listed in third_party/UPSTREAM with the commit we have).
#   tools/update_third_party.sh           show what is new upstream (changes nothing)
#   tools/update_third_party.sh --apply   copy the newest upstream code into third_party/ and update UPSTREAM (then review, test, commit)
set -euo pipefail
cd "$(dirname "$0")/.."
F=third_party/UPSTREAM; out=$(mktemp); new=0
grep -v '^#' "$F" | while read -r n url cur; do :; done
{ grep '^#' "$F"; } > "$out"
while read -r n url cur; do
  up=$(git ls-remote "$url" HEAD | cut -f1 | head -1)
  if [ "$cur" = "$up" ]; then printf '%-14s up to date (%s)\n' "$n" "${cur:0:7}"; echo "$n $url $cur" >> "$out"
  else
    printf '%-14s NEW upstream %s (we have %s)\n' "$n" "${up:0:7}" "${cur:0:7}"
    if [ "${1:-}" = "--apply" ]; then
      t=$(mktemp -d); git clone -q --depth 1 "$url" "$t/r"; rm -rf "$t/r/.git"
      rm -rf "third_party/$n"; mv "$t/r" "third_party/$n"; echo "$n $url $up" >> "$out"
    else echo "$n $url $cur" >> "$out"; fi
  fi
done < <(grep -v '^#' "$F")
[ "${1:-}" = "--apply" ] && cp "$out" "$F" && git status --short third_party && echo "Now read the changes, run the tests, and commit."
exit 0
