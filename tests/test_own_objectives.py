"""A project's own objectives in the report: the ones of the profile
version the assessment pins, worded as that set version words them, named next to the built-in
O1 ... O50 and ordered after them, by set code then number."""
from report_renderer.data import control_objectives as co
from report_renderer.data.vocab import with_own_objectives
from report_renderer.objective_order import objective_order

PID = "00000000-0000-0000-0000-000000000001"


def test_the_own_objectives_of_the_pinned_profile_are_read(monkeypatch):
    seen = {}

    def rows(sources, project_id, source, sql, params=None):
        seen["sql"], seen["params"] = sql, params
        return [{"objective_id": "BNK1", "dimension": "REQ2", "label": "Sign-off", "text": "Changes are signed off.",
                 "legal_basis": ""}]

    monkeypatch.setattr(co.db, "project_rows", rows)
    got = co.own_objectives(PID, PID, sources=None)
    assert got == [{"objective_id": "BNK1", "dimension": "REQ2", "label": "Sign-off",
                    "text": "Changes are signed off.", "legal_basis": ""}]
    assert "profile_version_id" in seen["sql"] and seen["params"]["s"] == PID


def test_own_objectives_are_named_beside_the_built_in_ones():
    labels = {"O1": {"macro": "REQ1 Human Agency and Oversight", "legal_basis": "AI Act Art. 14",
                     "label": "Operator oversight", "objective": "..."},
              "O5": {"macro": "REQ2 Technical Robustness and Safety", "legal_basis": "AI Act Art. 15",
                     "label": "Robustness", "objective": "..."}}
    own = [{"objective_id": "BNK1", "dimension": "REQ2", "label": "Sign-off", "text": "Changes are signed off.",
            "legal_basis": ""}]
    merged = with_own_objectives(labels, own)
    assert merged["BNK1"] == {"macro": "REQ2 Technical Robustness and Safety", "legal_basis": "",
                              "label": "Sign-off", "objective": "Changes are signed off."}
    assert merged["O1"] == labels["O1"]


def test_own_objectives_sort_after_the_built_in_set():
    assert sorted(["BNK10", "O24", "BNK9", "AAA1", "O3", "R1.1"], key=objective_order) == [
        "O3", "O24", "AAA1", "BNK9", "BNK10", "R1.1"]
