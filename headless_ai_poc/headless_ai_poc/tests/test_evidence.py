import shutil

from hai.experiments import ROOT
from hai.verify import _integrity, published, verify


def test_the_published_run_verifies():
    assert verify(write=False)


def test_the_verifier_notices_a_changed_byte(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(ROOT / "runs" / published(), run)
    assert _integrity(run)[0]
    facts = run / "facts.json"
    facts.write_text(facts.read_text().replace('"value": 1', '"value": 2', 1))
    ok, detail = _integrity(run)
    assert not ok and "facts.json" in detail
