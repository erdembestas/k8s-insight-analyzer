#!/usr/bin/env bash
set -euo pipefail

# Load optional mounted config (ConfigMap)
CONFIG_DIR=/etc/k8s-insight-analyzer/config
if [ -d "$CONFIG_DIR" ]; then
  echo "Loading config from $CONFIG_DIR"
fi

# If args provided, exec them (Helm can override command/args)
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Default behavior: decide which playbook to run based on MOCK_LLM
if [ "${MOCK_LLM:-0}" = "1" ]; then
  echo "MOCK_LLM=1 -> running dry-run single cluster pipeline"
  exec ansible-playbook playbooks/tmp_run_single_cluster.yml -v
else
  echo "Running full fleet analyzer (playbooks/analyze_fleet.yml)"
  exec ansible-playbook playbooks/analyze_fleet.yml -i inventories/local/hosts.yml -v
fi
