from pathlib import Path

import pytest

from extraceval import Config, ConfigError, load_config
from extraceval.extractors.pdfplumber import PdfplumberOptions


def test_defaults_run_all_installed_extractors() -> None:
    specs = Config().resolve_extractors()
    assert "pypdfium2" in [spec.name for spec in specs]
    assert all(spec.cls.is_available() for spec in specs)


def test_variants_and_options(tmp_path: Path) -> None:
    config_file = tmp_path / "extraceval.toml"
    config_file.write_text(
        """
        input = "data"
        extractors = ["pdfplumber", "pdfplumber-layout"]

        [options.pdfplumber-layout]
        tool = "pdfplumber"
        layout = true
        """
    )
    config = load_config(config_file)
    assert config.input == tmp_path / "data"
    plain, layout = config.resolve_extractors()
    assert (plain.name, plain.tool, plain.options) == (
        "pdfplumber",
        "pdfplumber",
        PdfplumberOptions(),
    )
    assert (layout.name, layout.tool) == ("pdfplumber-layout", "pdfplumber")
    assert layout.options == PdfplumberOptions(layout=True)


def test_variants_are_included_by_default() -> None:
    config = Config(options={"pypdf-layout": {"tool": "pypdf", "extraction_mode": "layout"}})
    assert "pypdf-layout" in [spec.name for spec in config.resolve_extractors()]


def test_pyproject_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.extraceval]\nsample = 3\n")
    monkeypatch.chdir(tmp_path)
    assert load_config().sample == 3


def test_no_config_file_gives_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config() == Config()


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"pdfplumber": {"layuot": True}}, "layuot"),
        ({"pdfplumber": {"layout": "sometimes"}}, "layout"),
        ({"thing": {"tool": "nope"}}, "unknown extractor 'nope'"),
    ],
)
def test_invalid_options_fail_loudly(options: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Config(extractors=list(options), options=options).resolve_extractors()


def test_unknown_top_level_key(tmp_path: Path) -> None:
    config_file = tmp_path / "extraceval.toml"
    config_file.write_text("smaple = 3\n")
    with pytest.raises(ConfigError, match="smaple"):
        load_config(config_file)


def test_override_ignores_none_and_validates() -> None:
    config = Config(sample=5).override(sample=None, input="other", seed=3)
    assert (config.sample, config.input, config.seed) == (5, Path("other"), 3)
