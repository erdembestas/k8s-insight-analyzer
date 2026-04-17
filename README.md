# k8s-insight-analyzer

**Version 0.1.0-beta** | **Release Date: 17.04.2026**

**⚠️ BETA VERSION - UNSTABLE**  
This is a beta release under active development. Features may change, and the software may contain bugs. Use in production environments at your own risk. Please report any issues you encounter.

Ansible-driven collection pipeline for Kubernetes/OpenShift fleet health analysis with an external LLM endpoint.

This repository is designed for **read-only** cluster inspection:

- collects per-cluster health snapshots
- normalizes noisy raw output into a compact JSON summary
- sends structured data to an OpenAI-compatible LLM API
- renders per-cluster Markdown reports

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Supported Commands & Platforms](#supported-commands--platforms)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Docker Image](#docker-image)
- [Helm Chart](#helm-chart)
- [Security & Privacy](#security--privacy)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Overview

This is a lightweight Ansible-driven toolkit for collecting Kubernetes/OpenShift cluster telemetry, normalizing it to structured JSON, enriching with optional RAG context, and producing short, actionable Markdown health reports using an LLM gateway.

The project is intended as a read-only inspection tool (no writes to clusters by default).

## How It Works

The system operates through a 5-stage pipeline that processes each cluster in your fleet sequentially:

### Stage 1: Cluster Data Collection

The system connects to each configured cluster and executes read-only kubectl/oc commands to gather comprehensive health telemetry:

1. **Cluster Version Check**: `kubectl version -o json`
   - Retrieves Kubernetes API server version and client version information

2. **Node Inventory**: `kubectl get nodes -o json`
   - Collects all node details including status, capacity, and conditions

3. **Namespace Enumeration**: `kubectl get ns -o json`
   - Lists all namespaces in the cluster

4. **Pod Status Across All Namespaces**: `kubectl get pods -A -o json`
   - Gathers pod status, restart counts, and container states from all namespaces

5. **Warning Events**: `kubectl get events -A --field-selector type=Warning -o json`
   - Collects all warning-level events from the past hour (configurable)

6. **Resource Usage - Nodes**: `kubectl top nodes --no-headers`
   - CPU and memory utilization for each node

7. **Resource Usage - Pods**: `kubectl top pods -A --no-headers`
   - CPU and memory usage for pods across all namespaces

8. **OpenShift-Specific Data** (when platform=openshift): `oc get clusteroperators -o json`
   - ClusterOperator status and conditions (OpenShift only)

### Stage 2: Data Normalization

Raw JSON and text outputs are processed through a Python normalizer that:

- Extracts key metrics and counts from verbose API responses
- Calculates summary statistics (ready nodes, pending pods, crash loops, etc.)
- Limits output size to prevent LLM token limits (configurable limits for events, pods, etc.)
- Optionally redacts sensitive cluster/node names for privacy
- Structures data into a clean JSON payload for LLM consumption

### Stage 3: Context Retrieval (RAG - Optional)

When enabled, the system searches local Markdown runbooks for relevant troubleshooting context:

- Keyword-based search against cluster issues found in telemetry
- Retrieves relevant sections from local documentation
- Enriches LLM prompts with domain-specific knowledge
- Helps provide more accurate and actionable recommendations

### Stage 4: LLM Analysis

The normalized telemetry (and optional RAG context) is sent to an OpenAI-compatible LLM API:

- Uses structured prompts with JSON telemetry data
- Requests analysis in specific JSON format with predefined fields
- Supports multiple LLM backends with fallback (OpenAI, Anthropic, etc.)
- Parses model responses into structured findings and recommendations

### Stage 5: Report Generation

LLM analysis results are rendered into human-readable Markdown reports:

- Executive summary with risk level assessment
- Critical findings with prioritized recommendations
- Actionable remediation steps with reasoning
- Raw telemetry summary for reference
- Timestamped reports saved per cluster

## Supported Commands & Platforms

### Kubernetes Platform Support

**Core Commands Executed:**

- `kubectl version -o json` - API server and client version info
- `kubectl get nodes -o json` - Node inventory and status
- `kubectl get ns -o json` - Namespace enumeration
- `kubectl get pods -A -o json` - Pod status across all namespaces
- `kubectl get events -A --field-selector type=Warning -o json` - Warning events
- `kubectl top nodes --no-headers` - Node resource utilization
- `kubectl top pods -A --no-headers` - Pod resource utilization

**Data Collected:**

- Node readiness and capacity information
- Pod status, restart counts, and container states
- Resource utilization metrics (CPU/memory)
- Warning events from all namespaces
- Cluster version information

### OpenShift Platform Support

**All Kubernetes commands above, plus OpenShift-specific:**

- `oc get clusteroperators -o json` - ClusterOperator health status
- `oc version` - OpenShift version information (via kubectl version)

**Additional Data Collected:**

- ClusterOperator conditions and availability
- OpenShift-specific component health
- Integrated platform services status

### Platform Detection & Command Selection

The system automatically detects the platform type from inventory configuration:

```yaml
clusters:
  - name: production-k8s
    context: prod-admin
    platform: kubernetes # Uses kubectl commands only

  - name: staging-openshift
    context: staging-admin
    platform: openshift # Uses kubectl + oc commands
```

**Command Execution Logic:**

1. Always executes core Kubernetes commands (kubectl)
2. Conditionally executes `oc get clusteroperators` when platform=openshift
3. Handles command failures gracefully (resource metrics may not be available)
4. Uses context-specific authentication for multi-cluster setups

### Current Limitations (Beta)

- **Read-Only Operations Only**: No cluster modifications or deployments
- **Basic Authentication**: Uses kubeconfig contexts (no advanced auth methods yet)
- **Limited Metrics Scope**: Focuses on core health indicators, not comprehensive monitoring
- **No Persistent Storage**: Reports generated on-demand, no historical tracking
- **Single LLM Call Per Cluster**: No iterative analysis or follow-up questions
- **Basic RAG Implementation**: Simple keyword matching, not semantic search

## Repository Structure

### Core Files

- **`ansible.cfg`** - Ansible configuration with YAML output format and collection paths
- **`requirements.txt`** - Python dependencies (pytest, ansible-lint, requests, PyYAML, jsonschema)
- **`Makefile`** - Common development commands (lint, test, clean)
- **`LICENSE`** - MIT license
- **`README.md`** - This documentation
- **`SECURITY.md`** - Security policy and vulnerability reporting
- **`CONTRIBUTING.md`** - Contribution guidelines
- **`CHANGELOG.md`** - Version history and changes

### Playbooks (`playbooks/`)

- **`analyze_fleet.yml`** - Main orchestration playbook for fleet analysis
  - Validates prerequisites (kubectl access, LLM configuration)
  - Creates artifact directories for each pipeline stage
  - Loops through each cluster executing the 5-stage pipeline
  - Handles errors gracefully and continues with remaining clusters

### Roles (`roles/`)

- **`collect_cluster_snapshot/`** - Executes kubectl/oc commands to gather raw cluster data
  - Runs all supported commands listed in "Supported Commands & Platforms"
  - Saves raw JSON/text output to artifacts/raw/{cluster}/
  - Handles both Kubernetes and OpenShift platforms automatically

- **`normalize_snapshot/`** - Processes raw data into structured JSON
  - Calls Python normalizer script with configurable limits
  - Applies redaction for privacy when enabled
  - Outputs clean JSON to artifacts/normalized/{cluster}.json

- **`retrieve_context/`** - RAG retrieval from local runbooks (optional)
  - Searches docs/runbooks/ for relevant troubleshooting content
  - Matches keywords from cluster issues to documentation sections
  - Outputs context JSON to artifacts/rag/{cluster}.json

- **`call_llm/`** - Sends data to LLM API for analysis
  - Builds prompts using Jinja2 templates
  - Supports multiple LLM backends with fallback
  - Parses structured JSON responses from models
  - Saves raw and parsed responses to artifacts/llm/

- **`render_report/`** - Generates final Markdown reports
  - Combines telemetry, LLM analysis, and RAG context
  - Renders human-readable reports with prioritized recommendations
  - Outputs to artifacts/reports/{cluster}.md

### Scripts (`scripts/`)

- **`normalize_snapshot.py`** - Python data normalization and redaction
  - Parses kubectl JSON outputs into summary statistics
  - Limits output size to prevent LLM token overflow
  - Handles both Kubernetes and OpenShift data formats

- **`retrieve_context.py`** - Simple keyword-based RAG retrieval
  - Searches local Markdown files for relevant content
  - Returns matching sections for LLM context enrichment

- **`llm_gateway.py`** - Multi-backend LLM API client
  - Supports OpenAI, Anthropic, and compatible APIs
  - Handles authentication, retries, and error recovery
  - Parses responses into structured analysis format

### Templates (`templates/`)

- **`llm_prompt.j2`** - Jinja2 template for LLM prompts
  - Structures telemetry data for model consumption
  - Includes RAG context when available
  - Requests specific JSON response format

- **`report.md.j2`** - Jinja2 template for Markdown reports
  - Formats LLM analysis into readable health reports
  - Includes risk levels, findings, and action items
  - Embeds raw telemetry summary for reference

### Docker (`docker/`)

- **`Dockerfile`** - Multi-stage build with Ansible collections
- **`entrypoint.sh`** - Container entrypoint script
- **`publish.sh`** - Helper script for building and publishing images

### Helm Chart (`charts/k8s-insight-analyzer/`)

- **`Chart.yaml`** - Chart metadata and dependencies
- **`values.yaml`** - Default configuration values
- **`templates/`** - Kubernetes manifests (Deployment, ServiceAccount, ConfigMap, Secret)
- **`examples/`** - Example values files for different configurations

### Configuration (`vars/`, `inventories/`)

- **`vars/llm_backends.example.yml`** - Example LLM backend configurations
- **`inventories/example/`** - Example inventory with cluster definitions
- **`inventories/local/`** - Local development inventory

### Mocks (`mocks/`)

- **`kubectl`** - Mock kubectl binary for dry-run testing
- **`oc`** - Mock oc binary for dry-run testing

### Documentation (`docs/`)

- **`runbooks/`** - Directory for Markdown runbooks (RAG knowledge base)

## Prerequisites

- **Python 3.11+** - Required for scripts and Ansible
- **Ansible 2.14+** (or ansible-core 2.15+) - For orchestration
- **`kubectl`** or **`oc`** - For real cluster collection (not needed for dry-run)
- **`helm`** - For chart linting and template tests (optional)
- **`docker`** - For building and running container images (optional)

## Installation

### Option 1: Clone and Setup (Recommended for Development)

1. **Clone the repository:**

   ```bash
   git clone https://github.com/erdembestas/k8s-insight-analyzer.git
   cd k8s-insight-analyzer
   ```

2. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Install Ansible collections:**

   ```bash
   ansible-galaxy collection install -r collections/requirements.yml
   ```

4. **Verify installation:**
   ```bash
   pytest -q  # Run unit tests
   helm lint charts/k8s-insight-analyzer  # Lint Helm chart
   ```

### Option 2: Docker Image

1. **Pull the published image:**

   ```bash
   docker pull ghcr.io/erdembestas/k8s-insight-analyzer:0.1.0
   ```

2. **Or build locally:**
   ```bash
   docker build -t k8s-insight-analyzer:0.1.0 -f docker/Dockerfile .
   ```

### Option 3: Helm Chart

1. **Add Helm repository:**

   ```bash
   helm repo add erdembestas https://erdembestas.github.io/helm-charts
   helm repo update
   ```

2. **Install the chart:**
   ```bash
   helm install k8s-insight-analyzer erdembestas/k8s-insight-analyzer \
     --set image.repository=ghcr.io/erdembestas/k8s-insight-analyzer \
     --set image.tag="0.1.0" \
     --set llm.apiTokenSecretName=your-llm-secret
   ```

## Configuration

### LLM Backend Setup

#### Single Provider Mode (Simple)

Set environment variables:

```bash
export LLM_API_URL="https://api.openai.com/v1"
export LLM_API_TOKEN="your-api-token"
export LLM_MODEL="gpt-4"
```

#### Gateway Mode (Multi-Provider)

1. Copy the example configuration:

   ```bash
   cp vars/llm_backends.example.yml vars/llm_backends.yml
   ```

2. Edit `vars/llm_backends.yml`:
   ```yaml
   backends:
     - name: openai
       api_url: https://api.openai.com/v1
       api_token: "{{ lookup('env', 'OPENAI_API_TOKEN') }}"
       model: gpt-4
       priority: 1
     - name: anthropic
       api_url: https://api.anthropic.com/v1
       api_token: "{{ lookup('env', 'ANTHROPIC_API_TOKEN') }}"
       model: claude-3-sonnet
       priority: 2
   ```

### Inventory Configuration

1. Copy example inventory:

   ```bash
   cp -r inventories/example inventories/production
   ```

2. Edit `inventories/production/hosts.yml`:

   ```yaml
   all:
     vars:
       artifacts_dir: "{{ playbook_dir }}/../artifacts"
     children:
       clusters:
         hosts:
           cluster1:
             name: production-cluster-1
             context: prod-cluster-1-admin
             platform: kubernetes
           cluster2:
             name: staging-openshift
             context: staging-ocp-admin
             platform: openshift
   ```

3. Configure group variables in `inventories/production/group_vars/all.yml`:

   ```yaml
   # LLM Configuration
   llm_api_url: "{{ lookup('env', 'LLM_API_URL') }}"
   llm_api_token: "{{ lookup('env', 'LLM_API_TOKEN') }}"
   llm_model: gpt-4

   # RAG Configuration
   enable_rag: true
   runbooks_dir: "{{ playbook_dir }}/../docs/runbooks"
   ```

### RAG Knowledge Base

1. Create runbooks directory:

   ```bash
   mkdir -p docs/runbooks
   ```

2. Add Markdown files with troubleshooting guides:
   ```
   docs/runbooks/
   ├── crashloop-backoff.md
   ├── image-pull-errors.md
   ├── node-pressure.md
   └── network-issues.md
   ```

## Usage

### Dry-Run Demo (Safe, No External Calls)

1. **Set up mock environment:**

   ```bash
   export PATH="$PWD/mocks:$PATH"
   export MOCK_LLM=1
   ```

2. **Run the demo:**

   ```bash
   ansible-playbook playbooks/analyze_fleet.yml -i inventories/local/hosts.yml
   ```

3. **Check generated artifacts:**
   ```bash
   ls -la artifacts/
   # artifacts/
   # ├── llm/
   # ├── normalized/
   # ├── rag/
   # ├── raw/
   # └── reports/
   ```

### Production Run

1. **Ensure kubectl/oc access:**

   ```bash
   kubectl config get-contexts  # Verify cluster access
   ```

2. **Set LLM credentials:**

   ```bash
   export LLM_API_URL="https://api.openai.com/v1"
   export LLM_API_TOKEN="sk-..."
   ```

3. **Run analysis:**
   ```bash
   ansible-playbook playbooks/analyze_fleet.yml -i inventories/production/hosts.yml
   ```

### Docker Container Usage

1. **Run with environment variables:**

   ```bash
   docker run --rm \
     -e LLM_API_URL="https://api.openai.com/v1" \
     -e LLM_API_TOKEN="your-token" \
     -v ~/.kube/config:/root/.kube/config \
     -v ./artifacts:/opt/k8s-insight-analyzer/artifacts \
     ghcr.io/erdembestas/k8s-insight-analyzer:0.1.0
   ```

2. **Run with mounted configuration:**
   ```bash
   docker run --rm \
     -v ./vars:/opt/k8s-insight-analyzer/vars \
     -v ./inventories:/opt/k8s-insight-analyzer/inventories \
     -v ~/.kube/config:/root/.kube/config \
     ghcr.io/erdembestas/k8s-insight-analyzer:0.1.0 \
     ansible-playbook playbooks/analyze_fleet.yml -i inventories/production/hosts.yml
   ```

## Docker Image

### Building

```bash
# Build locally
docker build -t k8s-insight-analyzer:0.1.0 -f docker/Dockerfile .

# Test the build
docker run --rm -e MOCK_LLM=1 -e LLM_API_TOKEN=dummy \
  -v "$PWD/mocks:/mocks" -v "$PWD:/opt/k8s-insight-analyzer" \
  -e PATH="/mocks:$PATH" \
  k8s-insight-analyzer:0.1.0 /bin/sh -c 'export PATH=/mocks:$PATH && /usr/local/bin/entrypoint.sh'
```

### Publishing

#### To GitHub Container Registry (GHCR)

1. **Create personal access token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Create token with `write:packages` permission

2. **Use the publish helper:**
   ```bash
   ./docker/publish.sh ghcr.io/erdembestas/k8s-insight-analyzer 0.1.0
   ```

#### To Docker Hub

```bash
# Login and push
docker login
docker tag k8s-insight-analyzer:0.1.0 your-dockerhub-username/k8s-insight-analyzer:0.1.0
docker push your-dockerhub-username/k8s-insight-analyzer:0.1.0
```

## Helm Chart

### Installation

1. **Update values with your image:**

   ```yaml
   # values.yaml
   image:
     repository: ghcr.io/erdembestas/k8s-insight-analyzer
     tag: "0.1.0"
   ```

2. **Create LLM secret:**

   ```bash
   kubectl create secret generic ops-llm-token \
     --from-literal=token="your-llm-api-token"
   ```

3. **Install the chart:**
   ```bash
   helm install k8s-insight-analyzer ./charts/k8s-insight-analyzer \
     -f charts/k8s-insight-analyzer/examples/single-model-rag.yaml
   ```

### Configuration Options

| Parameter                | Description                          | Default                                  |
| ------------------------ | ------------------------------------ | ---------------------------------------- |
| `image.repository`       | Container image repository           | `"ghcr.io/erdembestas/k8s-insight-analyzer"` |
| `image.tag`              | Container image tag                  | `"0.1.0"`                               |
| `llm.mode`               | LLM mode: `single` or `gateway`      | `"single"`                               |
| `llm.apiUrl`             | LLM API URL                          | `""`                                     |
| `llm.apiTokenSecretName` | Kubernetes secret name for API token | `""`                                     |
| `rag.enabled`            | Enable RAG retrieval                 | `false`                                  |
| `persistence.enabled`    | Enable PVC for artifacts             | `false`                                  |

### Examples

- **Single model with RAG:** `charts/k8s-insight-analyzer/examples/single-model-rag.yaml`
- **Multi-model gateway:** `charts/k8s-insight-analyzer/examples/multi-model-no-rag.yaml`
- **CronJob deployment:** `charts/k8s-insight-analyzer/examples/cronjob-mode.yaml`

## Security & Privacy

### Best Practices

- **Never commit secrets:** Use environment variables or external secret managers
- **Review artifacts:** Scan generated reports for sensitive data before sharing
- **Network isolation:** Run in isolated networks when possible
- **RBAC:** Use minimal required permissions for cluster access

### Data Handling

- **Redaction:** The normalizer includes options to redact cluster/node names
- **PII scanning:** Run `trufflehog` or similar tools against the repository
- **Audit logging:** Enable Ansible log collection for compliance

### LLM Security

- **API key rotation:** Regularly rotate LLM API tokens
- **Rate limiting:** Configure appropriate rate limits for your LLM provider
- **Content filtering:** Review LLM prompts and responses for sensitive data

## Testing

### Unit Tests

```bash
pytest -q  # Quick test run
pytest -v  # Verbose output
pytest --cov=scripts/  # Coverage report
```

### Helm Chart Testing

```bash
helm lint charts/k8s-insight-analyzer
helm template test-release charts/k8s-insight-analyzer -f charts/k8s-insight-analyzer/examples/single-model-rag.yaml
```

### Dry-Run Testing

```bash
export PATH="$PWD/mocks:$PATH"
export MOCK_LLM=1
ansible-playbook playbooks/analyze_fleet.yml -i inventories/local/hosts.yml
```

### Integration Testing

```bash
# Test with real cluster (requires cluster access)
ansible-playbook playbooks/analyze_fleet.yml -i inventories/production/hosts.yml --check
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

### Development Setup

1. **Fork and clone:**

   ```bash
   git clone https://github.com/erdembestas/k8s-insight-analyzer.git
   cd k8s-insight-analyzer
   ```

2. **Set up development environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pre-commit install
   ```

3. **Run tests:**
   ```bash
   make test
   make lint
   ```

### Code Quality

- **Linting:** `ansible-lint` for playbooks, `flake8` for Python
- **Testing:** `pytest` with coverage reporting
- **Pre-commit hooks:** Automated code quality checks

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

- **Name:** Erdem Bestas
- **Title:** System Engineer
- **Email:** erdembestaseem@gmail.com
