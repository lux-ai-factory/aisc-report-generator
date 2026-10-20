"""Reports name VAIR choices by their labels.

The qualification form speaks VAIR: its tables hold VAIR local names, and new columns for the system's
type and purpose and each risk field's term. The report shows each by VAIR's label, from the generated
vair_vocab.json; a value that is not a term, or a report without the file, shows the value itself, so
older cards and the golden outputs keep their bytes. Unit tests, no database.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from conftest import need

VAIR_VOCAB = Path(__file__).resolve().parents[3] / "apps/qualification/src/data/vair_vocab.json"
OLD_AIRO = {"affected": [{"id": "user", "label": "User (people who use the system)"}],
            "impactArea": [{"id": "right", "label": "Fundamental rights"}]}


def en(msgid, **params):
    from aisc_report_plugin_interface.i18n import fill

    return fill(msgid, params)


@pytest.fixture
def airo(tmp_path):
    p = tmp_path / "airo_vocab.json"
    p.write_text(json.dumps(OLD_AIRO))
    return str(p)


@pytest.fixture
def vocab(airo):
    return need("report_renderer.data.vocab", "airo_labels")(airo, str(VAIR_VOCAB))


def ctx(vocab):
    return SimpleNamespace(t=en, system={"number": 2, "description": None}, data=SimpleNamespace(vocab=vocab))


def text(html) -> str:
    return " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())


# The vocabulary.


def test_the_vair_labels_come_by_class(vocab):
    assert vocab["vair"]["Domain"]["PrivateService"] == "Private Service"
    assert vocab["vair"]["AreaOfImpact"]["RightToNondiscrimination"] == "Right To Non-discrimination"


def test_an_area_is_named_by_vair_and_an_old_area_id_still_by_its_old_label(vocab):
    assert vocab["impactArea"]["Right"] == "Right"
    assert vocab["impactArea"]["right"] == "Fundamental rights"
    assert vocab["affected"]["user"].startswith("User")


def test_a_vair_group_of_affected_people_is_named_by_its_label_and_ours_keep_theirs(airo, tmp_path):
    f = tmp_path / "vair_vocab.json"
    f.write_text(json.dumps({"classes": {"AISubject": [{"id": "JobApplicant", "label": "Job Applicant"}]}}))
    v = need("report_renderer.data.vocab", "airo_labels")(airo, str(f))
    assert v["affected"]["JobApplicant"] == "Job Applicant"
    assert v["affected"]["user"].startswith("User")


def test_without_the_vair_file_nothing_is_named_by_vair(airo):
    v = need("report_renderer.data.vocab", "airo_labels")(airo, None)
    assert v["vair"] == {}
    assert v["impactArea"] == {"right": "Fundamental rights"}


def test_the_vair_path_is_optional_in_the_environment():
    Sources = need("report_renderer.data", "Sources")
    env = {k: "x" for k in ("REPORT_PLATFORM_DATABASE_URL", "REPORT_SUPERSET_DATABASE_URL", "REPORT_PROJECT_DB_URL",
                            "REPORT_AIRO_VOCAB_PATH", "REPORT_OBJECTIVES_CSV_PATH")}
    assert Sources.from_env(env).vair_vocab_path is None
    assert Sources.from_env({**env, "REPORT_VAIR_VOCAB_PATH": "/data/vair_vocab.json"}).vair_vocab_path == \
        "/data/vair_vocab.json"


def test_label_of_falls_back_to_the_value():
    label_of = need("report_renderer.data.vocab", "vair_label")
    v = {"vair": {"Domain": {"PrivateService": "Private Service"}}}
    assert label_of(v, "Domain", "PrivateService") == "Private Service"
    assert label_of(v, "Domain", "finance") == "finance"
    assert label_of({"vair": {}}, "Domain", "PrivateService") == "PrivateService"


# The readers read the new columns.


def test_the_card_and_its_risks_read_the_vair_columns(monkeypatch):
    q = pytest.importorskip("report_renderer.data.qualification")
    seen = []
    monkeypatch.setattr(q.db, "project_one", lambda s, p, m, sql, params: seen.append(sql) or None)
    monkeypatch.setattr(q.db, "project_rows", lambda s, p, m, sql, params: seen.append(sql) or [])
    pid, sid = "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"
    q.card(pid, sid, sources=None)
    q.risks(pid, sid, sources=None)
    card_sql, risk_sql = seen
    for col in ("system_type", "purpose"):
        assert f"q.{col}" in card_sql, col
    for col in ("source_term", "consequence_term", "impact_term", "control_term", "follow_up_control_term"):
        assert f"r.{col}" in risk_sql, col


# The AI card block.

CARD = {"system_name": "MCAS", "company": "Creditum", "description": "d", "target_use_case": "u",
        "target_users": "t", "intended_deployers": None, "system_type": "NarrowAI",
        "purpose": "AssessingCreditworthiness", "target_system_tags": ["NaturalLanguageGeneration", "scoring"],
        "sector_tags": ["PrivateService"], "market_form_tags": ["SafetyComponent"],
        "locality_tags": ["PubliclyAccessibleSpace"]}


def render_card(vocab, card=CARD, **options):
    AiCardBlock = need("report_renderer.blocks.ai_card", "AiCardBlock")
    opts = {"show_components": False, "show_tags": True, "show_graph_stats": False, **options}
    return text(AiCardBlock().render({"card": card, "components": [], "graph": None, "newest_newer": None},
                                     opts, ctx(vocab)).html)


def test_the_tags_are_vair_labels_under_the_report_s_own_headings(vocab):
    # the headings stay as reports have always had them, so an older report keeps its bytes
    t = render_card(vocab)
    for shown in ("Target system Natural Language Generation, scoring", "Sector Private Service",
                  "Market form Safety Component", "Locality Publicly Accessible Space"):
        assert shown in t, shown


def test_the_system_type_and_purpose_are_shown_by_their_labels(vocab):
    t = render_card(vocab)
    assert "Type of AI system Narrow AI" in t
    assert "Intended purpose Assessing Creditworthiness" in t


def test_a_card_without_them_shows_no_empty_row(vocab):
    t = render_card(vocab, card={**CARD, "system_type": None, "purpose": None})
    assert "Type of AI system" not in t and "Intended purpose" not in t


# The risk classification block.

RISK = {"position": 0, "risk": "Wrongly refused", "source": "Thin data", "source_term": "ErroneousInputData",
        "vulnerability": None, "consequence": "Refused", "consequence_term": None,
        "impact_term": "UnfavourableTreatment", "affected": "user", "impact_areas": ["RightToNondiscrimination"],
        "control": "Human review", "control_term": "HumanOversightMeasure",
        "follow_up_control": "Override", "follow_up_control_term": "OverridingOutcome"}


def render_risks(vocab, risk=RISK):
    Block = need("report_renderer.blocks.risk_classification", "RiskClassificationBlock")
    opts = {"show_chains": True, "show_impact_areas": True, "stated_risk_class": "not_determined"}
    return text(Block().render({"card": {"id": "c"}, "graph": None, "risks": [risk], "newest_newer": None},
                               opts, ctx(vocab)).html)


def test_each_field_shows_its_text_then_its_vair_term(vocab):
    t = render_risks(vocab)
    assert "Source Thin data (VAIR: Erroneous Input Data)" in t
    assert "Control Human review (VAIR: Human Oversight Measure)" in t
    assert "Follow-up control Override (VAIR: Overriding Outcome)" in t
    assert "Consequence Refused" in t and "Refused (VAIR" not in t


def test_the_kind_of_harm_and_the_areas_are_vair_labels(vocab):
    t = render_risks(vocab)
    assert "Kind of harm Unfavourable Treatment" in t
    assert "Impact areas Right To Non-discrimination" in t


def test_an_older_risk_without_terms_renders_as_it_did(vocab):
    old = {k: v for k, v in RISK.items() if not k.endswith("_term")}
    old["impact_areas"] = ["right"]
    t = render_risks(vocab, old)
    assert "VAIR" not in t and "Kind of harm" not in t
    assert "Impact areas Fundamental rights" in t


# Changes since an earlier version.


def test_changed_tags_are_named_by_vair(vocab):
    tag_text = need("report_renderer.blocks.changes_since", "tag_text")
    assert tag_text({"PrivateService", "Education"}, "sector_tags", vocab) == "Education, Private Service"
    assert tag_text({"finance"}, "sector_tags", vocab) == "finance"
