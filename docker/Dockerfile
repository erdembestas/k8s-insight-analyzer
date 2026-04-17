FROM python:3.11-slim

LABEL maintainer="your-email@example.com"

WORKDIR /opt/k8s-insight-analyzer

# Install runtime deps if provided
COPY requirements.txt /tmp/requirements.txt
COPY collections/requirements.yml /tmp/collections-requirements.yml
RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc \
  libpq-dev \
  && if [ -s /tmp/requirements.txt ]; then pip install --no-cache-dir -r /tmp/requirements.txt; fi \
  && if [ -s /tmp/collections-requirements.yml ]; then ansible-galaxy collection install -r /tmp/collections-requirements.yml; fi \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /tmp/requirements.txt /tmp/collections-requirements.yml

# Copy project files
COPY . /opt/k8s-insight-analyzer

# Entrypoint
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/opt/k8s-insight-analyzer:$PATH"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["ansible-playbook", "playbooks/analyze_fleet.yml", "-i", "inventories/local/hosts.yml"]
