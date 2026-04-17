# Node NotReady Runbook

When nodes become NotReady, check the kubelet logs, network, and resource pressure.

Steps:

- Check `kubectl describe node <node>`
- Inspect kubelet logs
- Verify disk pressure

Known signals: NotReady, disk pressure, kubelet
