#!/usr/bin/env bash
# Stand up the isolated ACME demo guardrails on the CURRENT cluster context.
# Creates: namespace acme-demo (PSA restricted), a ResourceQuota, and a
# ValidatingAdmissionPolicy (+ binding) scoped to acme-demo. Nothing shared is touched.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Context: $(oc whoami) @ $(oc whoami --show-server)"
echo "Applying demo guardrails..."
oc apply -f "${HERE}/manifests/00-namespace.yaml"
oc apply -f "${HERE}/manifests/01-resourcequota.yaml"
oc apply -f "${HERE}/manifests/02-policy-acme-rules.yaml"

# Let the agent's MCP identity WRITE in THIS namespace only.
# The in-cluster openshift-mcp-server authenticates as its own service account
# (openshift-mcp:openshift-mcp-server), which is bound cluster-wide to the read-only
# `view` role. Without this, the agent's create/scale/update is rejected at RBAC --
# BEFORE the ACME admission policy can evaluate it -- so the demo can't show the cluster
# deciding on content. This grants `edit` scoped to acme-demo (still view-only elsewhere);
# teardown deletes the namespace, taking this binding with it. Nothing shared is touched.
oc create rolebinding openshift-mcp-edit \
  --clusterrole=edit \
  --serviceaccount=openshift-mcp:openshift-mcp-server \
  -n acme-demo --dry-run=client -o yaml | oc apply -f -

# The ValidatingAdmissionPolicy does not enforce the instant it is created -- the API
# server needs a few seconds to compile and propagate the binding. Probe until a known
# non-compliant Deployment is actually rejected, so the demo never races the policy.
#
# We grep the rejection for our own policy name. A bare "the apply failed" check would
# report success if the probe failed for an UNRELATED reason (namespace not ready,
# RBAC, a typo in the probe) -- a false green that would only show up on camera.
echo
echo -n "Waiting for the admission policy to start enforcing"
probe='{"apiVersion":"apps/v1","kind":"Deployment","metadata":{"name":"acme-vap-probe","namespace":"acme-demo"},"spec":{"replicas":0,"selector":{"matchLabels":{"app":"acme-vap-probe"}},"template":{"metadata":{"labels":{"app":"acme-vap-probe"}},"spec":{"containers":[{"name":"c","image":"registry.access.redhat.com/ubi9/ubi-micro:9.8"}]}}}}'
enforcing=false
for i in $(seq 1 30); do
  out="$(echo "${probe}" | oc apply --dry-run=server -f - 2>&1 || true)"
  if echo "${out}" | grep -q "ACME platform standards"; then
    enforcing=true
    echo " enforcing."
    break
  fi
  echo -n "."
  sleep 2
done

if [ "${enforcing}" != true ]; then
  echo
  echo "ERROR: the admission policy is NOT enforcing after ~60s."
  echo "Last response from the API server:"
  echo "${out}"
  echo
  echo "Check: oc get validatingadmissionpolicy acme-deployment-rules -o yaml"
  exit 1
fi

echo
echo "Guardrails in place. Deployments in acme-demo now enforce all 3 ACME rules."
echo "Next: deploy the compliant workload (manifests/10-*) or let the agent create it."
