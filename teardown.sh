#!/usr/bin/env bash
# Remove EVERYTHING this demo created. Leaves the cluster exactly as it was.
# Deletes the acme-demo namespace (and all workloads + the ResourceQuota inside it)
# plus the cluster-scoped ValidatingAdmissionPolicy and its binding.
set -euo pipefail

echo "Context: $(oc whoami) @ $(oc whoami --show-server)"
echo "Tearing down the ACME demo..."
oc delete validatingadmissionpolicybinding acme-deployment-rules-binding --ignore-not-found
oc delete validatingadmissionpolicy acme-deployment-rules --ignore-not-found
oc delete namespace acme-demo --ignore-not-found

echo
echo "Done. Nothing from this demo remains on the cluster."
