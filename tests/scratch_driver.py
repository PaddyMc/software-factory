"""Driver that runs tests/test_web_markdown.py against scratch_md.py. Throwaway."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory.web
import scratch_md

sys.modules["factory.web.markdown"] = scratch_md
factory.web.markdown = scratch_md

import pytest

raise SystemExit(pytest.main(["-q", "tests/test_web_markdown.py", "-x", "--no-header"]))
