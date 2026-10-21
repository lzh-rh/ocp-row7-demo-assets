# Connect Claude Code to an OpenShift MCP server

This kit's **live agent beat (3)** needs Claude Code talking to an OpenShift MCP server.
The approach here connects to an **OpenShift MCP server already running in the cluster**
(it does not install one). Claude launches a local helper that opens a private,
authenticated tunnel to that in-cluster Service; the MCP tools execute in the cluster.

> The rest of the kit — `setup.sh`, `teardown.sh`, and every manifest — works with plain
> `oc` and needs none of this. Only the live agent beat uses MCP.

## What ships in this kit

| File | Role |
|---|---|
| `.mcp.json` | Project-scoped MCP registration. Points Claude at `connect-openshift-mcp.py`. |
| `connect-openshift-mcp.py` | Default helper. Private `oc port-forward` tunnel to an in-cluster MCP **Service**, with verified service TLS. No public Route needed. |
| `mcp-tunnel-tls.cjs` | TLS helper the Python script preloads so verification checks the service DNS name through the loopback tunnel. Keep it next to the `.py`. |
| `connect-openshift-route.sh` | **Alternative** helper for clusters that expose the MCP server as a public **Route** (uses `mcp-remote` directly). Swap it into `.mcp.json` if your cluster has a Route instead of an internal Service. |

## Requirements

On your machine, on PATH: `oc`, `python3`, Node.js, and `mcp-remote`
(`npm install -g mcp-remote`; tested with `0.15.1`). The cluster must already run an
OpenShift MCP Service and publish its service-CA ConfigMap — this connection reads them,
it does not create them.

## Start using it

1. Log into the intended cluster with its `oc login`. From the **kit directory**, confirm
   the target and that the MCP Service exists:

   ```bash
   oc whoami --show-server
   oc whoami
   oc get clusterversion version
   oc get service openshift-mcp-server -n openshift-lightspeed   # adjust ns/name to your cluster
   claude mcp get openshift
   ```

   If your MCP Service lives in a different namespace or under a different name, pass them to
   the helper via `.mcp.json` args, e.g. `--namespace <ns> --service <name>` (defaults:
   `openshift-lightspeed` / `openshift-mcp-server`, HTTPS port `8443`).

2. Start Claude from the **same terminal** (so it inherits your `oc` login / `KUBECONFIG`):

   ```bash
   claude
   ```

   Open `/mcp`, select `openshift`, then ask something read-only to verify end to end:

   > Use the openshift MCP server to read config.openshift.io/v1 ClusterVersion named
   > version. Report its version without making changes.

   Expect a successful read matching the CLI. On each new cluster, repeat — the helper uses
   the current kubeconfig context at startup.

## How it connects

```text
Claude Code
  -> connect-openshift-mcp.py + mcp-remote, over stdio
  -> private `oc port-forward` on 127.0.0.1, verified HTTPS
  -> <namespace>/openshift-mcp-server:8443/mcp
  -> OpenShift API using the logged-in user's bearer token
```

The helper reads credentials from kubeconfig at startup and passes the token to `mcp-remote`
through an environment variable — the token is **not** written into `.mcp.json`, the helper
source, or process arguments, and there is no token to paste. It also reads the public
`openshift-service-ca.crt` ConfigMap; `mcp-tunnel-tls.cjs` makes TLS verify the service DNS
name through the loopback tunnel while keeping the loopback HTTP Host this server requires.
Certificate verification stays enabled. The temporary CA file and the tunnel are cleaned up
when the helper exits. No public Route is created.

The project `.mcp.json` registers this at **project scope**. When Claude first loads the
folder it will ask you to approve the project MCP server; approve it, then verify with
`claude mcp get openshift` and `/mcp`. A user- or local-scoped `openshift` entry from a
previous setup would take precedence over this project file — remove it if you want the
kit's config to win (`claude mcp remove openshift --scope local`).

## Tool availability (varies by cluster)

A given deployment advertises its own tool set. On one test cluster the server exposed **25
tools** (resource reads, pod/project, Helm, and metrics such as `list_metrics` /
`execute_instant_query`) but **did not** advertise `resources_create_or_update` — the tool
the Skill's Deployment-creation step relies on. Check `/mcp`'s live tool list on your
cluster; if a write tool you need is absent, that is a server configuration matter, not a
connection failure. Some advertised tools can make changes, so treat the inventory as
read/write, not read-only. All writes remain subject to OpenShift RBAC and the ACME
admission policy, and the Skill still enforces its human-approval gate.

## Troubleshooting

| Symptom | Check and action |
|---|---|
| `oc whoami` fails | Fix the login, API network/DNS, or API cert trust first. |
| Service or CA ConfigMap missing | `oc get svc openshift-mcp-server -n <ns>` and `oc get cm openshift-service-ca.crt -n <ns>`. Verify the cluster's MCP install and namespace. |
| Tunnel won't start | Confirm the MCP pod is Ready and your identity can read the Service/pods and create `pods/portforward` in that namespace. |
| TLS verification fails | Check the service's serving cert and public CA; keep verification enabled. A different service DNS name needs matching helper args. |
| Tool reports `Unauthorized` | Log in again and restart Claude — the helper captures the token at startup. |
| Tool reports `Forbidden` | Check RBAC for that operation/namespace. Connected ≠ authorized for everything. |
| MCP drops after a pod restart | Reconnect `openshift` in `/mcp`, or restart Claude to open a fresh tunnel. |
| Claude shows a different/old MCP entry | Run `claude mcp get openshift` from this directory; remove any higher-precedence user/local-scoped entry and restart. |
| CLI and Claude show different clusters | Exit Claude, log into the intended cluster in the same terminal, restart, repeat the read check. |

## Sources

- [Claude Code MCP scope precedence](https://code.claude.com/docs/en/mcp#scope-hierarchy-and-precedence)
- [mcp-remote](https://github.com/punkpeye/mcp-remote)
- [OpenShift MCP Server](https://github.com/openshift/openshift-mcp-server)

> Verified against a test cluster on 2026-10-20: Claude reported `Scope: Local config` /
> `Status: ✔ Connected`; MCP `initialize`, `tools/list`, and a read-only `resources_get`
> returning the cluster's OpenShift version all succeeded through the helper, with TLS
> accepting the correct service identity and rejecting a wrong hostname. Live observations
> describe that cluster and may change after an upgrade or reconfiguration.
