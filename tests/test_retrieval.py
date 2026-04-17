import json
from pathlib import Path
from scripts.retrieve_context import match_documents


def test_match_documents_simple(tmp_path):
    # create temporary markdown files
    d = tmp_path / "runbooks"
    d.mkdir()
    f1 = d / "run1.md"
    f1.write_text("This runbook covers NotReady nodes and kubelet issues.")
    f2 = d / "run2.md"
    f2.write_text("This is unrelated doc.")

    signals = ["NotReady"]
    docs = [f1, f2]
    matches = match_documents(signals, docs)
    assert len(matches) == 1
    assert matches[0]["path"].endswith("run1.md")
