from scripts.normalize_snapshot import parse_top_nodes, parse_top_pods


def test_parse_top_nodes_standard():
    text = """
node1 100m 5% 512Mi 10%
node2 200m 10% 1Gi 20%
"""
    parsed = parse_top_nodes(text, limit=10)
    assert parsed[0]["name"] == "node1"
    assert parsed[0]["cpu"] == "100m"
    assert parsed[0]["cpu_percent"] == "5%"
    assert parsed[0]["memory"] == "512Mi"


def test_parse_top_nodes_minimal():
    text = "node1 100m"
    parsed = parse_top_nodes(text, limit=10)
    assert parsed[0]["name"] == "node1"
    assert parsed[0]["cpu"] == "100m"


def test_parse_top_pods_standard():
    text = """
namespace1 pod-a 50m 64Mi
namespace2 pod-b 100m 128Mi
"""
    parsed = parse_top_pods(text, limit=10)
    assert parsed[0]["namespace"] == "namespace1"
    assert parsed[0]["name"] == "pod-a"
    assert parsed[0]["cpu"] == "50m"
    assert parsed[0]["memory"] == "64Mi"


def test_parse_top_pods_three_columns():
    text = "namespace1 pod-a 50m"
    parsed = parse_top_pods(text, limit=10)
    assert parsed[0]["cpu"] == "50m"
