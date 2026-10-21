# AI-Assisted Compliant Workload Creation

A self-contained demo that runs in its **own `acme-demo` namespace** on an OpenShift
cluster, enforced by **native OpenShift admission only**. It touches nothing shared — no
RHACS changes, no existing namespaces — and tears down completely.

## What enforces the 3 ACME rules for Deployments

| Rule | Enforced by |
|---|---|
| 1. No root (hardened securityContext) | `ValidatingAdmissionPolicy` (at apply) + **PSA `restricted`** (backstop) |
| 2. Requests + limits (cpu & memory) | `ValidatingAdmissionPolicy` + **ResourceQuota** (backstop) |
| 3. Ownership labels (`app`, `team`, `cost-center`) | `ValidatingAdmissionPolicy`; `team` and `cost-center` must equal the namespace labels |

The `ValidatingAdmissionPolicy` (VAP) is the headline gate — it rejects a non-compliant
Deployment at `oc apply` with a clear per-rule message. PSA + ResourceQuota are independent
native backstops: even if the VAP were removed, root pods and limit-less pods still can't run.

## Files

```
manifests/
  00-namespace.yaml             acme-demo namespace (PSA restricted; owner labels team/cost-center)
  01-resourcequota.yaml         forces requests+limits (backstop for rule 2)
  02-policy-acme-rules.yaml     ValidatingAdmissionPolicy + binding (all 3 rules)
  10-compliant-deployment.yaml  compliant Deployment (no-agent fallback)
  20-trap-generic-ai.yaml       non-compliant Deployment (rejected on all 3 rules)
  30-privileged-proof.yaml      optional: compliant EXCEPT privileged:true (rejected by PSA + VAP)
setup.sh      apply the guardrails
teardown.sh   delete everything this demo created
.claude/skills/acme-deployment-rules/SKILL.md   the Skill for Claude Code
```

## Prereqs

- Logged into a cluster (`oc whoami` works) with rights to create a namespace, a
  ResourceQuota, and a cluster-scoped `ValidatingAdmissionPolicy`.
- **Live agent walkthrough only:** Claude Code connected to an OpenShift MCP server. Run
  `claude` **from this directory** so it loads the Skill and the project `.mcp.json`. Needs
  `oc`, Node.js, and `mcp-remote` (`npm install -g mcp-remote`) on PATH. Setup and
  troubleshooting: [MCP-CONNECTION.md](MCP-CONNECTION.md).

## Run it

```bash
# 1. Stand up the guardrails (idempotent)
./setup.sh

# 2. Launch Claude Code from THIS directory, then confirm the connection
claude
/mcp        # expect: openshift — Connected
```

Paste these prompts **one at a time**. The Skill drafts each change, shows it to you, and
**waits for your approval** before applying — the human-in-the-loop gate.

| # | Say to the agent | Expected |
|---|---|---|
| 1 | Deploy my payments API to the acme-demo namespace. gRPC service on port 50051, image `us-central1-docker.pkg.dev/google-samples/microservices-demo/paymentservice:v0.10.2`. | ✅ Hardened Deployment + Service generated with the namespace's owner labels, approved, pod **Running**. |
| 2 | The payments-api is moving to the platform team. Set team=platform on it. | 🚫 **Blocked (rule 3)** — `team` must equal the namespace owner label (`payments`); a workload can't claim another team's label. |
| 3 | We've got a load test this afternoon. Scale payments-api to 3 replicas. | ✅ Scaled to 3; still compliant, within quota. |
| 4 | Those pods are tight on memory. Raise the memory limit on payments-api to 512Mi. | ✅ Updated; still declares cpu+memory requests AND limits. |
| 5 | Load test pushed to next week. Roll that memory change back to 256Mi. | ✅ Reverted to 256Mi; still compliant. |

```bash
# Reset between runs (keeps the guardrails)
oc delete deploy,svc payments-api -n acme-demo --ignore-not-found

# Full teardown when done
./teardown.sh
```

### Without the agent (plain `oc`)

```bash
oc apply -f manifests/20-trap-generic-ai.yaml       # non-compliant → admission denied, rule messages
oc apply -f manifests/10-compliant-deployment.yaml  # compliant     → created + pod Running
oc apply -f manifests/30-privileged-proof.yaml      # optional       → rejected by PSA and the VAP
```

## Isolation guarantee

Everything created lives in `acme-demo` except one cluster-scoped `ValidatingAdmissionPolicy`
(+ binding) that only enforces in `acme-demo`. `teardown.sh` removes all of it. No shared
RHACS policy, operator, or namespace is modified.
