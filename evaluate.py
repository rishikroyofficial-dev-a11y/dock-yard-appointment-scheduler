"""evaluate.py - compares validate.py's FINDINGS with 
the ground truth.
Kept separate so the validator itself can never see 
 the answers.
Usage: python evaluate.py --scale full --out output
"""
import argparse
import csv
import json
import os

from config import ANOMALY_TYPES


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", default="starter")
    p.add_argument("--out", default="output")
    a = p.parse_args()
    base = os.path.join(a.out, a.scale)
    found = json.load(open(os.path.join(base, "validation", "findings.json")))
    gt = list(csv.DictReader(open(os.path.join(base, "ground_truth", "ground_truth.csv"), newline="")))

    def truth(t, table):
        return {g["record_id"] for g in gt if g["issue_type"] == t and g["table_name"] == table}

    rows = {}
    for t in ANOMALY_TYPES:
        if t == "DOCK_OVERLAP":
            want, pairs = truth(t, "appointments"), found[t]["pairs"]
            hit_pairs = [pr for pr in pairs if want & set(pr)]
            covered = want & {i for pr in pairs for i in pr}
            rows[t] = (len(pairs), len(hit_pairs), len(want), len(covered))     # unit = overlapping pair
        else:
            table = "checkin_events" if t == "CHECKIN_BEFORE_DATE" else "appointments"
            got, want = set(found[t]["records"]), truth(t, table)
            rows[t] = (len(got), len(got & want), len(want), len(got & want))
    out = {}
    print(f"{'issue type':26}{'flagged':>8}{'correct':>9}{'injected':>10}{'found':>7}{'precision':>11}{'recall':>8}")
    for t, (flagged, correct, injected, found_n) in rows.items():
        prec = correct / flagged if flagged else 1.0
        rec = found_n / injected if injected else 1.0
        out[t] = {"flagged": flagged, "correct": correct, "injected": injected, "found": found_n,
                  "precision": round(prec, 4), "recall": round(rec, 4)}
        print(f"{t:26}{flagged:8}{correct:9}{injected:10}{found_n:7}{prec:11.0%}{rec:8.0%}")
    shifts_got, shifts_want = set(found["LABOR_SHIFT_UNAVAILABLE"]["shifts"]), truth("LABOR_SHIFT_UNAVAILABLE", "labor_shifts")
    print(f"cancelled shifts (root cause): flagged {len(shifts_got)}, injected {len(shifts_want)}, match = {shifts_got == shifts_want}")
    with open(os.path.join(base, "validation", "evaluation.json"), "w", newline="\n") as fh:
        json.dump(out, fh, indent=2); fh.write("\n")


if __name__ == "__main__":
    main()