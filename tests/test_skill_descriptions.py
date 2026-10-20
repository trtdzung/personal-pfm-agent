"""The skill loader keeps only the first 1024 characters of a description: a longer one silently loses its tail (routing hints, the 'only proposes' line)."""

from pathlib import Path

import pytest
import yaml

SKILLS = sorted((Path(__file__).resolve().parent.parent / "skills" / "project").glob("*/SKILL.md"))
MAX_DESCRIPTION = 1024


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_description_fits_the_loader_limit(path):
    meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert meta["name"] == path.parent.name
    assert len(meta["description"]) <= MAX_DESCRIPTION, len(meta["description"])
