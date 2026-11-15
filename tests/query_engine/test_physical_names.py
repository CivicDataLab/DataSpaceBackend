"""Layer 2: the 63-byte column-name cut (PN1)."""

from api.services.query_engine.physical_names import physical_column_name


def test_a_short_ascii_header_is_unchanged() -> None:
    assert physical_column_name("IMR (%)") == "IMR (%)"


def test_a_70_character_header_is_cut_to_63_bytes() -> None:
    header = "Percentage of children age 6-59 months who are anaemic (%) in the district"
    cut = physical_column_name(header)
    assert len(cut.encode("utf-8")) == 63
    assert header.startswith(cut)


def test_a_devanagari_header_is_cut_on_a_character_boundary() -> None:
    header = "जिले में एनीमिया से पीड़ित बच्चों का प्रतिशत"
    cut = physical_column_name(header)
    assert len(cut.encode("utf-8")) <= 63
    assert len(cut.encode("utf-8")) > 60
    assert header.startswith(cut)
    cut.encode("utf-8").decode("utf-8")  # never half a character
