"""End-to-end closed-loop test: init → record-raw(conclusion) → distill → assemble-context → convert-to-sop → gate → approve → retrain → list."""
from typer.testing import CliRunner

from mlagent.cli import app

runner = CliRunner()


def test_e2e_closed_loop(tmp_path):
    root = tmp_path / "project_memory"

    # 1. init
    assert runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False).exit_code == 0

    # 2. record-raw with conclusion
    raw = tmp_path / "raw.yaml"
    raw.write_text(
        "id: raw_001\ntype: run\ncreated_at: 2026-07-03T10:00:00+08:00\ngoal: Improve AUC\n"
        "conclusion:\n  hypothesis: top-50 helps\n  outcome: confirmed\n  summary: auc +0.03\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["record-raw", str(raw), "--memory-root", str(root)], catch_exceptions=False).exit_code == 0

    # 3. distill (insert experience)
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        "ops:\n- decision: insert\n  experience:\n"
        "    id: exp_001\n    type: pitfall\n    summary: leakage\n    detail: d\n"
        "    confidence: high\n    needs_review: false\n"
        "    source_raw_records: [raw_memory/runs/raw_001.yaml]\n"
        "    created_at: 2026-07-03T10:30:00+08:00\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["distill", str(plan), "--memory-root", str(root)], catch_exceptions=False).exit_code == 0

    # 4. assemble-context (experience injected)
    ctx = runner.invoke(app, ["assemble-context", "Improve AUC", "--memory-root", str(root)], catch_exceptions=False)
    assert ctx.exit_code == 0
    assert "exp_001" in ctx.stdout

    # 5. convert-to-sop
    assert runner.invoke(
        app,
        ["convert-to-sop", "--sop-name", "baseline", "--version", "v001", "--source-type", "exploration",
         "--source-evidence", "raw_memory/runs/raw_001.yaml", "--background", "b", "--reason", "r",
         "--memory-root", str(root)],
        catch_exceptions=False,
    ).exit_code == 0

    # 6. approve WITHOUT gate → fails (exit 2)
    perf = tmp_path / "perf.yaml"
    perf.write_text("primary_metric:\n  name: auc\n  value: 0.91\ndataset_version: d1\nvalidation_protocol: holdout\n")
    fail = runner.invoke(app, ["approve-sop", "--sop-name", "baseline", "--version", "v001",
                               "--reviewer", "h", "--approval-note", "ok", "--performance-path", str(perf),
                               "--memory-root", str(root)], catch_exceptions=False)
    assert fail.exit_code == 2  # gate not passed

    # 7. set-gate-result → approve → succeeds
    assert runner.invoke(app, ["set-gate-result", "--sop-name", "baseline", "--version", "v001",
                               "--memory-root", str(root)], catch_exceptions=False).exit_code == 0
    assert runner.invoke(app, ["approve-sop", "--sop-name", "baseline", "--version", "v001",
                               "--reviewer", "h", "--approval-note", "ok", "--performance-path", str(perf),
                               "--memory-root", str(root)], catch_exceptions=False).exit_code == 0

    # 8. retrain → loads approved SOP
    rt = runner.invoke(app, ["retrain", "baseline", "v001", "--memory-root", str(root)], catch_exceptions=False)
    assert rt.exit_code == 0
    assert "approved" in rt.stdout.lower()

    # 9. list-sops → shows baseline/v001 approved
    ls = runner.invoke(app, ["list-sops", "--memory-root", str(root)], catch_exceptions=False)
    assert ls.exit_code == 0
    assert "baseline" in ls.stdout
    assert "v001" in ls.stdout

    # 10. status → shows counts
    st = runner.invoke(app, ["status", "--memory-root", str(root)], catch_exceptions=False)
    assert st.exit_code == 0
    assert "Raw memory records: 1" in st.stdout
    assert "Experience records: 1" in st.stdout
    assert "Skill versions: 1" in st.stdout
