import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed in this environment")
def test_wheel_includes_customer_data_json(tmp_path):
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=REPO_ROOT,
        check=True,
    )
    wheels = sorted(dist_dir.glob("*.whl"))
    assert wheels, "expected `uv build --wheel` to produce a .whl file"
    with zipfile.ZipFile(wheels[-1]) as archive:
        names = archive.namelist()
        for customer_id in ("CIF_0001", "CIF_0002", "CIF_0003"):
            assert any(name.endswith(f"{customer_id}.json") for name in names), names
