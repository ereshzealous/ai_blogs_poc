"""L2 · Authorization invariant and security tests: the 14 named production invariants (authz/invariants.py).

    python3 -m unittest discover -s tests -v

One test per invariant, one subtest per named case. The number of invariants is fixed at 14; cases may grow.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from authz.invariants import INVARIANTS  # noqa: E402


class Invariants(unittest.TestCase):
    def test_exactly_14_named_invariants(self):
        self.assertEqual([i for i, _, _ in INVARIANTS], [f"AUTHZ-INV-{n:02d}" for n in range(1, 15)])


def _make(iid: str, name: str, fn):
    def test(self):
        for case, ok in fn():
            with self.subTest(f"{iid} · {case}"):
                self.assertTrue(ok, f"{iid} {name}: {case}")
    test.__doc__ = f"{iid} {name}"
    return test


for _iid, _name, _fn in INVARIANTS:
    _slug = re.sub(r"[^a-z0-9]+", "_", _name.lower()).strip("_")
    setattr(Invariants, f"test_{_iid[-2:]}_{_slug}", _make(_iid, _name, _fn))


if __name__ == "__main__":
    unittest.main()
