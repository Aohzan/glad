"""Coverage test for legacy finance/views.py module file."""

import importlib.util
from pathlib import Path


def test_load_legacy_finance_views_module_file():
    module_path = Path(__file__).resolve().parents[1] / "views.py"
    spec = importlib.util.spec_from_file_location(
        "finance_legacy_views_file", module_path
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "index" in module.__all__
    assert "chart_data" in module.__all__
