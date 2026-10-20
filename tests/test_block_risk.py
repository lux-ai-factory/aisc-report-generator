"""Risk classification block. Operators come from the card's JSON-LD; the risk class is stated by
the editor."""
import pytest

from conftest import assert_no_foreign_data, render_one

pytestmark = pytest.mark.db


def test_operators_from_the_card(deps):
    t, s, _, result = render_one(deps, "risk_classification")
    assert "Acme AI (provider)" in t          # isProvidedBy, by its rdfs:label
    assert "Retail Bank (deployer)" in t      # isDeployedBy
    assert "urn:aisc:user:officer" in t       # hasAIUser without a label: the IRI
    assert s["status"] == "ok"
    assert_no_foreign_data(result["html"])


def test_risk_class_not_determined_by_default(deps):
    t, *_ = render_one(deps, "risk_classification")
    assert "Not determined" in t


def test_risk_class_stated_by_the_editor(deps):
    t, *_ = render_one(deps, "risk_classification", stated_risk_class="high")
    assert "high (stated by the report editor; the qualification does not classify risk)" in t.lower()


def test_chains_in_position_order_with_labels(deps):
    t, *_ = render_one(deps, "risk_classification")
    assert t.index("Bias against applicants") < t.index("Opaque refusals")
    assert "Operator (the company providing or running the system)" in t   # affected, labelled
    assert "User (people who use the system or are affected by it)" in t
    for free in ("Training data", "Historic bias", "Unfair refusals", "Bias audit", "Quarterly review"):
        assert free in t
    assert "Health" in t and "Safety" in t
    assert "fundamental_rights" in t                                        # no label: raw id


def test_impact_areas_can_be_hidden(deps):
    t, *_ = render_one(deps, "risk_classification", show_impact_areas=False)
    assert "Health" not in t and "fundamental_rights" not in t


def test_chains_can_be_hidden(deps):
    t, *_ = render_one(deps, "risk_classification", show_chains=False)
    assert "Bias against applicants" not in t
    assert "Acme AI (provider)" in t


def test_risk_text_is_escaped(deps):
    _, _, node, result = render_one(deps, "risk_classification")
    assert "<script>alert(1)</script>" not in result["html"]
    assert node.find("script") is None


@pytest.mark.parametrize("stated,label", [("high", "High"), ("prohibited", "Prohibited"), ("limited", "Limited"),
                                            ("minimal", "Minimal")])
def test_the_stated_class_prints_its_label_not_its_id(deps, stated, label):
    """The block printed the enum id ("high (stated ...") instead of the label the
    composer shows ("High")."""
    t, *_ = render_one(deps, "risk_classification", stated_risk_class=stated)
    assert f"{label} (stated by the report editor;" in t


def test_empty_without_operators_chains_or_stated_class(deps):
    _, s, _, _ = render_one(deps, "risk_classification", project="C", system="C_V1")
    assert s["status"] == "empty"


def test_a_stated_class_alone_is_not_empty(deps):
    _, s, _, _ = render_one(deps, "risk_classification", project="C", system="C_V1", stated_risk_class="minimal")
    assert s["status"] != "empty"


def test_stale_when_a_newer_card_exists(deps):
    _, s, _, _ = render_one(deps, "risk_classification", system="A_V1")
    assert s["status"] == "stale" and "Newer results exist for version 2." in s["notices"]


# one section per risk, not a table: a table's rows grow too tall
def test_each_risk_is_its_own_section(deps):
    _, _, node, _ = render_one(deps, "risk_classification")
    assert node.find("table") is None
    risks = node.find_all("section", class_="risk")
    titles = [r.find("h3").get_text(strip=True) for r in risks]
    assert titles[0].startswith("Bias against applicants") and titles[1].startswith("Opaque refusals")
    first = risks[0]
    labels = [dt.get_text(strip=True) for dt in first.find_all("dt")]
    assert labels[:4] == ["Source", "Vulnerability", "Consequence", "Affected"]
    assert "Control" in labels and "Follow-up control" in labels and "Impact areas" in labels


def test_a_risk_section_leaves_out_what_the_card_left_empty(deps):
    _, _, node, _ = render_one(deps, "risk_classification", show_impact_areas=False)
    for r in node.find_all("section", class_="risk"):
        labels = [dt.get_text(strip=True) for dt in r.find_all("dt")]
        assert "Impact areas" not in labels
        for dd in r.find_all("dd"):
            assert dd.get_text(strip=True), "no empty field is shown"
