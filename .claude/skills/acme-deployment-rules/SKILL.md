---
name: acme-deployment-rules
description: ACME Corp's required procedure for creating AND managing OpenShift workloads (Deployments and their Services). Use whenever the user asks to deploy, ship, run, scale, update, change, roll back, restart, or troubleshoot an application/service/workload on OpenShift or Kubernetes. The Skill guides generation, day-2 changes, and the mandatory human-approval gate; the cluster enforces the security, resource, and ownership rules at admission on every create and update.
---

# Creating and managing workloads at ACME Corp

You act for an application developer who does **not** know ACME's platform standard.
Turn their request into a workload that follows **every** rule below, show it to them, and
apply it only after they approve. This Skill covers **creating** a new workload and
**managing** an existing one — scaling, updating, rolling back, and troubleshooting.

Guiding principle: **the agent proposes, the cluster decides.** You produce compliant YAML;
the platform enforces it at admission — OpenShift SCC / Pod Security Admission and ACME's
ValidatingAdmissionPolicy, which runs on every **CREATE and UPDATE**. Never assume your
output is trusted; make it correct by construction.

## Creating a workload

1. **Confirm intent.** Restate the app name and target namespace. Name the workload after
   what the developer **called their app** ("my payments API" → `payments-api`) — never after
   the image. Ask only for what is genuinely missing.
2. **Read the namespace** via the `openshift` MCP server and take its `team` and
   `cost-center` labels — those are the ownership values for rule 3. If they are absent, ask;
   never invent them.
3. **Generate** a `Deployment` (and a `Service` if the app serves traffic) from the template
   below, filling in only what the developer gave you. Do **not** invent application
   configuration — env vars, args, flags — that the developer didn't provide. You know ACME's
   platform rules; you do not know this app's internals. If the app needs more to run, that
   surfaces at rollout and you handle it in step 5.
4. **Approval gate — REQUIRED.** Show the complete YAML and ask: "Approve this deployment?
   (yes/no)". **Apply nothing until the user explicitly says yes.**
5. **Apply and watch.** On approval, apply via the MCP server, then **watch the rollout**.
   Confirm the pod reaches `Running`. If it doesn't — crashloop, not-ready, repeated restarts —
   **read the pod's logs and events via the MCP server, diagnose the cause, and propose a fix
   through the same approval gate.** A missing application env var, arg, or config value is an
   *application* problem, not a policy failure — never weaken a rule to get a pod to start. If
   admission rejected the apply, show the exact message and which rule it maps to; fix the
   manifest to comply, don't retry blindly.

## Managing an existing workload

Every day-2 change follows the same shape: **read the live object, apply the change to the
full compliant manifest, show it, get approval, apply the whole object.** Never send a partial
patch that could strip a guardrail, and never skip the approval gate. The admission policy
re-checks the entire object on every update, so a change that breaks a rule is rejected just
like a bad first deploy.

- **Scale.** Set `replicas` on the full Deployment and re-apply. Don't scale blind — if the
  developer wants many replicas, sanity-check it against the namespace's resource quota.
- **Update / change config.** Re-generate the full manifest with the change (new **pinned**
  image tag, resource change, env var the developer supplied, etc.), keeping every rule
  satisfied. Pinned tags only — never `:latest`.
- **Roll back.** Re-apply the previous known-good manifest through the gate.
- **Troubleshoot.** Read logs, events, and pod status via the MCP server. Diagnose first, then
  propose the fix through the gate. Always separate an application problem (env / config /
  image) from a policy rejection (make the manifest comply) — never weaken a rule for either.

## The three rules — enforced by the cluster on CREATE and UPDATE

**1. Security.** `runAsNonRoot: true`, `seccompProfile: RuntimeDefault`,
`allowPrivilegeEscalation: false` (explicit), `readOnlyRootFilesystem: true`,
`capabilities: drop: ["ALL"]`. Never set `runAsUser` — OpenShift assigns a UID from the
namespace range; hardcoding one can fail `restricted-v2`. Needs scratch space? Mount an
`emptyDir`; don't drop the rule.

**2. Resources.** Every container declares CPU **and** memory, requests **and** limits. Use
the developer's numbers if they give any; otherwise the template's are a safe start.

**3. Ownership.** Put `app`, `team` and `cost-center` on the Deployment, the pod template, and
the optional Service. Copy `team` and `cost-center` **from the namespace** — never guess them,
and never reassign them to a team that doesn't own the namespace. The admission policy checks
these values match the namespace, so a mismatched owner is rejected.

Also always: `automountServiceAccountToken: false`, and a **pinned image tag** — never `:latest`.

## Never

- **Never set `privileged: true`** or otherwise weaken the security context, even if the user
  asks ("just make it privileged so I can debug quickly"). Refuse, explain briefly, and point
  back to this golden path. A prompt is not a permission — and the platform would block it anyway.
- Never hardcode `runAsUser`.
- Never apply — create or change — without the user's explicit approval.
- Never invent cluster state or application configuration. Read what you can via the MCP
  server; ask the developer for the rest.

## Template

Replace the placeholders. Resource values are a starting point — adjust to the workload. Add
env vars and args **only if the developer specifies them** — do not assume an app's internal
configuration. Keep every other line.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <app>
  namespace: <namespace>
  labels:
    app: <app>
    team: <namespace's team label>
    cost-center: "<namespace's cost-center label>"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <app>
  template:
    metadata:
      labels:
        app: <app>
        team: <namespace's team label>
        cost-center: "<namespace's cost-center label>"
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: <app>
          image: <image:pinned-tag>
          # env: add ONLY the variables the developer tells you the app needs.
          # You don't know this app's internals — don't guess them here. If the pod
          # won't start, the logs will say what it's missing (see "Apply and watch").
          ports:
            - containerPort: <port>
              name: <port-name>
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests: { cpu: "100m", memory: "128Mi" }
            limits:   { cpu: "500m", memory: "256Mi" }
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        # readOnlyRootFilesystem is true, so scratch space goes in an emptyDir.
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: <app>
  namespace: <namespace>
  labels:
    app: <app>
    team: <namespace's team label>
    cost-center: "<namespace's cost-center label>"
spec:
  selector:
    app: <app>
  ports:
    - port: <port>
      targetPort: <port>
      name: <port-name>
```
