#!/bin/bash
# Self-contained MCP launcher for the ocp-row7-demo-assets kit.
#
# Discovers the openshift-mcp-server Route in whatever cluster `oc` is currently
# logged into, then bridges Claude Code (stdio) to it with mcp-remote. Switching
# clusters needs only `oc login` -- nothing in this kit changes.
#
# Wired up by this folder's .mcp.json as the "openshift" MCP server.
#
# Pass --url to just print the discovered endpoint and exit (a quick sanity check
# after `oc login` to a new sandbox).
#
# Portability note: .mcp.json references this script by ABSOLUTE path. If you clone
# the kit to another machine/path, update that path. `oc` and `mcp-remote` must be
# on PATH.
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

die() { echo "openshift-mcp: $*" >&2; exit 1; }

command -v oc         >/dev/null || die "oc not found on PATH"
command -v mcp-remote >/dev/null || die "mcp-remote not found; run: npm install -g mcp-remote"
oc whoami >/dev/null 2>&1 || die "can't reach the cluster as a logged-in user -- run 'oc login' and check VPN/network. Detail: $(oc whoami 2>&1 | head -1)"

# Preferred location, then any route that looks like the MCP server.
host=$(oc get route openshift-mcp-server -n openshift-mcp \
         -o jsonpath='{.spec.host}' 2>/dev/null || true)
if [ -z "$host" ]; then
  host=$(oc get route -A \
    -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" "}{.spec.host}{"\n"}{end}' 2>/dev/null \
    | grep -E '^openshift-mcp/|/openshift-mcp-server ' \
    | head -1 | awk '{print $2}' || true)
fi
[ -n "$host" ] || die "no openshift-mcp-server route found on $(oc whoami --show-server 2>/dev/null)"

url="https://${host}/mcp"

if [ "${1:-}" = "--url" ]; then
  echo "$url"
  exit 0
fi

echo "openshift-mcp: using $url" >&2
exec mcp-remote "$url"
