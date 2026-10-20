"""Objective ids O1 ... O50 are listed in number order: O9 before O10, which string order would not
give. An id of the older numbering (such as R1.1) sorts after every O id."""
from report_renderer.data import control_objectives as co
from report_renderer.objective_order import objective_order


def test_o9_before_o10_and_old_ids_last():
    assert sorted(["O10", "R1.1", "O9", "O1"], key=objective_order) == ["O1", "O9", "O10", "R1.1"]


def test_the_selected_objectives_come_in_catalogue_order(monkeypatch):
    monkeypatch.setattr(co.db, "project_one", lambda *a, **k: {"objective_ids": ["O10", "O9", "O24"]})
    pid = "00000000-0000-0000-0000-000000000001"
    assert co.objective_ids(pid, pid, sources=None) == ["O9", "O10", "O24"]


def test_the_mapped_objectives_come_in_catalogue_order(monkeypatch):
    monkeypatch.setattr(co.db, "project_one", lambda *a, **k: None)
    monkeypatch.setattr(co.db, "project_rows",
                        lambda *a, **k: [{"objective_id": "O10"}, {"objective_id": "O2"}])
    pid = "00000000-0000-0000-0000-000000000001"
    assert co.objective_ids(pid, pid, sources=None) == ["O2", "O10"]
