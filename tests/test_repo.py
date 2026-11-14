"""Repo hygiene and honesty checks: the docs must match what the scripts really print."""

import io
import json
import re
import subprocess
from pathlib import Path

import pytest

import mesh_report as mr

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "agensi" / "desk-mesh-doctor"
EXAMPLES = SKILL / "examples"


def tracked_text_files():
    skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (skip & set(p.relative_to(ROOT).parts)) and p.suffix not in {".png", ".pyc"}:
            yield p


def test_license_names_only_the_author():
    text = (ROOT / "LICENSE").read_text()
    assert text.splitlines()[0] == "MIT License" and "Copyright (c) 2026 FinnTech3" in text


def test_no_forbidden_names_or_attribution_anywhere():
    # Built from pieces so this file does not contain the words it forbids.
    banned = ["cl" + "aude", "anth" + "ropic", "copi" + "lot", "chat" + "gpt", "open" + "ai", "gem" + "ini", "AI-gen" + "erated",
              "twin" + "desk", "inu" + "ka", "syner" + "gy", "barr" + "ier", "input " + "leap", "kde " + "connect", "phone " + "link",
              "tail" + "scale", "zero" + "tier"]  # fmt: skip
    for path in tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for word in banned:
            assert word.lower() not in text, f"{word!r} found in {path.relative_to(ROOT)}"


def test_no_agent_config_folders_or_files():
    names = {p.name for p in ROOT.rglob("*") if ".git" not in p.parts}
    assert not ({".cl" + "aude", "CLAU" + "DE.md", "AGENTS.md"} & names)


def test_the_listing_title_fits_agensis_limit():
    rows = dict(re.findall(r"(?m)^\|\s*([A-Za-z ]+?)\s*\|\s*(.+?)\s*\|\s*$", (ROOT / "agensi" / "LISTING.md").read_text()))
    assert len(rows["Title"]) <= 60 and rows["Title"].startswith("Desk Mesh Doctor")


def test_skill_frontmatter_parses_with_a_real_yaml_parser():
    yaml = pytest.importorskip("yaml")
    text = (SKILL / "SKILL.md").read_text()
    data = yaml.safe_load(text.split("---")[1])
    assert data["name"] == "desk-mesh-doctor" and data["version"] == "1.0.0"
    assert len(data["description"]) < 1024 and len(data["summary"]) <= 300
    assert "Use when" in data["description"] and "Do not use for" in data["description"]
    assert data["docs_url"] == "https://github.com/FinnTech3/desk-mesh-doctor"
    assert len(data["tags"]) <= 10 and len(data["keywords"]) <= 10 and len(data["use_cases"]) <= 8


def test_skill_md_follows_the_delivery_rules():
    text = (SKILL / "SKILL.md").read_text()
    assert "Requires:" in text and "temporary file" in text and "delete the file afterwards" in text
    assert not re.search(r"(?m)^\s*(\$\s*)?python3?\s+(\./)?scripts/", text)
    for heading in ("## Running the scripts", "## Output", "## Edge cases and errors", "## Rules"):
        assert heading in text
    assert text.count("\n") < 500


def test_every_script_and_reference_named_in_the_skill_exists():
    text = (SKILL / "SKILL.md").read_text()
    for rel in set(re.findall(r"`((?:scripts|references)/[\w.-]+)`", text)):
        assert (SKILL / rel).is_file(), rel
    for name in ("macos", "windows", "linux", "android", "ios", "router-and-network", "vpn"):
        assert f"{name}.md" in text


def test_the_example_json_files_parse_and_come_from_the_scripts():
    for name in ("lab-laptop-local", "lab-desk-local", "lab-laptop-to-desk-blocked", "lab-desk-to-laptop",
                 "lab-laptop-to-desk-fixed"):  # fmt: skip
        doc = json.loads((EXAMPLES / f"{name}.json").read_text())
        assert doc["tool"] in {"mesh_local", "mesh_link"} and doc["version"] == "1.0.0"


def report_for(*names):
    return mr.build(mr.read_docs("\n".join((EXAMPLES / n).read_text() for n in names)))


def rendered(rep, capsys):
    mr.render(rep)
    return capsys.readouterr().out


def test_the_blocked_report_in_the_examples_is_what_the_script_prints(capsys):
    rep = report_for("lab-laptop-local.json", "lab-desk-local.json", "lab-laptop-to-desk-blocked.json",
                     "lab-desk-to-laptop.json")  # fmt: skip
    assert rendered(rep, capsys) == (EXAMPLES / "lab-report-blocked.md").read_text()
    assert rep["problem"] is True
    assert json.loads((EXAMPLES / "lab-report-blocked.json").read_text()) == rep


def test_the_fixed_report_in_the_examples_is_what_the_script_prints(capsys):
    rep = report_for("lab-laptop-local.json", "lab-desk-local.json", "lab-laptop-to-desk-fixed.json",
                     "lab-desk-to-laptop.json")  # fmt: skip
    assert rendered(rep, capsys) == (EXAMPLES / "lab-report-fixed.md").read_text()
    assert rep["problem"] is False


def test_the_sample_session_quotes_both_reports_verbatim():
    session = (EXAMPLES / "sample-session.md").read_text()
    for name in ("lab-report-blocked.md", "lab-report-fixed.md"):
        assert (EXAMPLES / name).read_text().rstrip("\n") in session


def test_the_sample_session_states_its_limits_up_front():
    head = (EXAMPLES / "sample-session.md").read_text()[:1800]
    assert "virtual machine" in head and "namespaces" in head and "not run on real machines" in head


def test_the_listing_demo_numbers_match_the_captured_session():
    """The listing quotes the text run in the sample session, so every figure must appear there verbatim."""
    session = (EXAMPLES / "sample-session.md").read_text().split("## Part 2")[1]
    listing = " ".join((ROOT / "agensi" / "LISTING.md").read_text().split())
    lat = re.search(r"desk\$ python3 mesh_link.py peer.*?latency on port 7001: (\d+)/(\d+) answered, min [\d.]+ median ([\d.]+) "
                    r"p95 ([\d.]+) max [\d.]+ jitter ([\d.]+) ms", session, re.S)
    answered, sent, median, p95, jitter = lat.groups()
    assert f"{answered} of {sent} samples answered, median {median} ms, p95 {p95} ms, jitter {jitter} ms" in listing
    ms = re.findall(r"port 7001\s+open\s+([\d.]+) ms", session)
    assert f"open in {ms[0]} ms" in listing and f"`open` in {ms[1]} ms" in listing
    timeout = re.search(r"port 7001\s+timeout\s+([\d.]+) ms", session).group(1)
    assert f"timed out after {float(timeout) / 1000:.0f} s" in listing


def test_the_example_json_files_say_what_the_session_says_they_say():
    blocked = json.loads((EXAMPLES / "lab-laptop-to-desk-blocked.json").read_text())
    fixed = json.loads((EXAMPLES / "lab-laptop-to-desk-fixed.json").read_text())
    assert blocked["summary"]["status"] == "filtered" and blocked["ports"][0]["status"] == "timeout"
    assert fixed["summary"]["status"] == "ok" and fixed["ports"][0]["status"] == "open"


def test_the_checker_is_clean_on_the_shipped_skill():
    import agensi_build as ab

    findings = ab.check(SKILL) + ab.check_listing(SKILL.parent / "LISTING.md")
    assert findings == []


def test_git_history_is_one_commit_by_the_author_when_a_repo_exists():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    log = subprocess.run(["git", "log", "--format=%an|%ae"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
    lines = log.split()
    assert len(lines) == 1 and lines[0] == "FinnTech3|72574388+FinnTech3@users.noreply.github.com"


def test_stdin_handling_of_the_report_is_text_only(monkeypatch):
    monkeypatch.setattr(mr.sys, "stdin", io.StringIO(""))
    assert mr.main([]) == 2
