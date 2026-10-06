import csv

from laubmann_kg.review.regions import load_region_decisions

FIELDS = ["region_uid", "decision", "reason", "duplicate_of", "completeness", "crop", "agreement", "reviewed_by"]


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def test_machine_drop_needs_two_sources(tmp_path):
    path = tmp_path / "regions.csv"
    write(path, [
        {"region_uid": "r_a", "decision": "drop", "reason": "duplicate", "duplicate_of": "r_b", "agreement": "2", "reviewed_by": "machine:x"},
        {"region_uid": "r_c", "decision": "drop", "reason": "blank", "agreement": "1", "reviewed_by": "machine:x"},
        {"region_uid": "r_b", "decision": "keep", "completeness": "complete", "agreement": "2", "reviewed_by": "machine:x"},
    ])
    d = load_region_decisions(str(path))
    assert d["r_a"].drop and d["r_a"].duplicate_of == "r_b"
    assert not d["r_c"].drop
    assert d["r_b"].completeness == "complete"


def test_new_crop_and_unknown_completeness(tmp_path):
    path = tmp_path / "regions.csv"
    write(path, [{"region_uid": "r_d", "decision": "keep", "completeness": "cut off", "crop": "regions_v2/p/r_d.jpg",
                  "agreement": "2", "reviewed_by": "machine:x"},
                 {"region_uid": "r_e", "decision": "keep", "completeness": "maybe", "agreement": "1", "reviewed_by": "machine:x"}])
    d = load_region_decisions(str(path))
    assert d["r_d"].completeness == "cut off" and d["r_d"].crop == "regions_v2/p/r_d.jpg"
    assert d["r_e"].completeness is None


def test_reviewer_file_wins(tmp_path):
    machine, human = tmp_path / "m.csv", tmp_path / "h.csv"
    write(machine, [{"region_uid": "r_a", "decision": "drop", "reason": "duplicate", "agreement": "2", "reviewed_by": "machine:x"}])
    write(human, [{"region_uid": "r_a", "decision": "keep", "reviewed_by": "reviewer"}])
    assert not load_region_decisions(str(machine), str(human))["r_a"].drop
