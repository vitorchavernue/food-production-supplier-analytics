"""The Apache Hop project must be consistent before it ever reaches a server.

Checks the files the way Hop reads them: every pipeline and workflow is valid XML, every action points to a
file that exists, every transform uses a connection defined in hop/metadata, and connections hold only
variables (the passwords come from the environment of the run, never from the repository).
"""

import json
import re
import xml.etree.ElementTree as ET

from food_dw.config import ROOT

HOP = ROOT / "hop"
WORKFLOW = HOP / "workflows" / "load_warehouse.hwf"
PIPELINES = sorted((HOP / "pipelines").glob("*.hpl"))
CONNECTIONS = {json.loads(p.read_text())["name"]: json.loads(p.read_text()) for p in (HOP / "metadata" / "rdbms").glob("*.json")}


def project_path(path: str):
    return HOP / path.replace("${PROJECT_HOME}/", "")


def test_every_file_is_valid_xml():
    for path in [WORKFLOW, *PIPELINES]:
        ET.parse(path)


def test_workflow_actions_point_to_existing_files():
    root = ET.parse(WORKFLOW).getroot()
    for action in root.iter("action"):
        kind = action.findtext("type")
        if kind == "PIPELINE":
            assert project_path(action.findtext("filename")).resolve().exists(), action.findtext("name")
        if kind == "SQL":
            assert project_path(action.findtext("sqlfilename")).resolve().exists(), action.findtext("name")


def test_every_pipeline_is_run_by_the_workflow():
    actions = ET.parse(WORKFLOW).getroot().iter("action")
    used = {project_path(a.findtext("filename")).name for a in actions if a.findtext("type") == "PIPELINE"}
    assert used == {p.name for p in PIPELINES}


def test_hops_connect_existing_transforms_and_actions():
    for path in PIPELINES:
        root = ET.parse(path).getroot()
        names = {t.findtext("name") for t in root.iter("transform")}
        for hop in root.find("order").iter("hop"):
            assert hop.findtext("from") in names and hop.findtext("to") in names, path.name
    root = ET.parse(WORKFLOW).getroot()
    names = {a.findtext("name") for a in root.iter("action")}
    for hop in root.find("hops").iter("hop"):
        assert hop.findtext("from") in names and hop.findtext("to") in names


def test_transforms_use_defined_connections():
    for path in [WORKFLOW, *PIPELINES]:
        for element in ET.parse(path).getroot().iter("connection"):
            assert element.text in CONNECTIONS, f"{path.name}: {element.text}"


def test_connections_hold_only_variables():
    for name, meta in CONNECTIONS.items():
        settings = next(iter(meta["rdbms"].values()))
        for field in ("hostname", "port", "username", "password"):
            assert re.fullmatch(r"\$\{[A-Z_]+\}", settings[field]), f"{name}.{field}"


def test_extractions_read_only_changed_rows():
    """Every extraction except the reconciliation totals reads only rows changed since the watermark."""
    for path in PIPELINES:
        if path.stem == "extract_source_totals":
            continue
        sql = " ".join(t.findtext("sql") or "" for t in ET.parse(path).getroot().iter("transform"))
        assert "etl.watermark" in sql and "DT_ATUALIZACAO > CAST(? AS DATE)" in sql, path.name
