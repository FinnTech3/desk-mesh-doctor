"""Each script must work alone: the delivery model hands it over as text, to be run from a temporary file."""

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "agensi" / "desk-mesh-doctor" / "scripts"
NAMES = ["mesh_local.py", "mesh_link.py", "mesh_report.py"]


@pytest.fixture
def lone(tmp_path):
    """Copy each script into an empty folder of its own, the way an agent would write it out."""
    folder = tmp_path / "tmp"
    folder.mkdir()

    def copy(name):
        target = folder / f"run_{name}"
        shutil.copy(SCRIPTS / name, target)
        return target

    return copy, folder


def run(args, cwd, stdin=None):
    return subprocess.run([sys.executable, "-I", *map(str, args)], cwd=cwd, input=stdin, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("name", NAMES)
def test_the_script_is_under_the_size_limit(name):
    assert len((SCRIPTS / name).read_bytes()) <= 20 * 1024


@pytest.mark.parametrize("name", NAMES)
def test_the_script_imports_only_the_standard_library(name):
    tree = ast.parse((SCRIPTS / name).read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add((node.module or "").split(".")[0])
    assert modules <= set(sys.stdlib_module_names)


@pytest.mark.parametrize("name", NAMES)
def test_the_script_never_shells_out_or_evaluates(name):
    text = (SCRIPTS / name).read_text()
    for bad in ("shell=True", "os.system", "eval(", "exec(", "__import__", "pickle"):
        assert bad not in text


@pytest.mark.parametrize("name", NAMES)
def test_help_works_from_an_empty_folder(lone, name):
    copy, folder = lone
    r = run([copy(name), "--help"], folder)
    assert r.returncode == 0 and "usage:" in r.stdout and r.stderr == ""


def test_local_runs_alone_and_prints_json(lone):
    copy, folder = lone
    r = run([copy("mesh_local.py"), "--json", "--label", "alone"], folder)
    assert r.returncode in (0, 1) and json.loads(r.stdout)["label"] == "alone" and "Traceback" not in r.stderr
    assert list(folder.iterdir()) == [folder / "run_mesh_local.py"]  # it wrote nothing


def test_link_peer_and_listen_run_alone(lone, open_port):
    copy, folder = lone
    r = run([copy("mesh_link.py"), "peer", "127.0.0.1", "--ports", str(open_port), "--samples", "3", "--json"], folder)
    assert r.returncode == 0 and json.loads(r.stdout)["summary"]["status"] == "ok"
    r = run([copy("mesh_link.py"), "listen", "0"], folder)
    assert r.returncode == 2 and r.stdout == ""
    assert list(folder.iterdir()) == [folder / "run_mesh_link.py"]


def test_report_runs_alone_from_stdin(lone):
    copy, folder = lone
    local_doc = {"tool": "mesh_local", "kind": "local", "label": "x", "hostname": "x", "interfaces": [], "findings": []}
    r = run([copy("mesh_report.py"), "--json"], folder, stdin=json.dumps(local_doc))
    assert r.returncode == 0 and json.loads(r.stdout)["devices"][0]["name"] == "x"
    r = run([copy("mesh_report.py")], folder, stdin="")
    assert r.returncode == 2 and "error:" in r.stderr


def test_an_exit_code_of_1_is_a_finding_not_a_crash(lone, closed_port):
    copy, folder = lone
    r = run([copy("mesh_link.py"), "peer", "127.0.0.1", "--ports", str(closed_port), "--samples", "1"], folder)
    assert r.returncode == 1 and "findings:" in r.stdout and r.stderr == ""
