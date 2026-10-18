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


def test_the_docker_image_keeps_the_files_the_jar_endpoint_reads_at_runtime():
    # jar_endpoint.py reads prompts/*.md when a request arrives; an ignore rule for them would only fail in production
    ignored = [
        line.strip() for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for runtime_file in ("prompts/jar_cover.md", "prompts/jar_distribute.md"):
        assert (REPO_ROOT / runtime_file).is_file(), runtime_file
    assert not [rule for rule in ignored if rule in ("prompts", "prompts/", "*.md", "**/*.md")], ignored
    for module in ("jar_endpoint.py", "jar_checks.py", "ui_guard.py", "llm.py"):
        assert module not in ignored, module
