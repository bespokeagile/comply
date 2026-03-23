"""Section 9: SARIF / SBOM / JUnit import."""
import pytest

pytestmark = [pytest.mark.comply]


SAMPLE_SARIF = {
    "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "test-scanner", "rules": [
            {"id": "CWE-79",
             "shortDescription": {"text": "XSS vulnerability"}},
        ]}},
        "results": [{
            "ruleId": "CWE-79",
            "level": "error",
            "message": {"text": "Found XSS in handler.py"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "handler.py"},
                "region": {"startLine": 42},
            }}],
        }],
    }],
}

SAMPLE_SBOM = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.4",
    "components": [
        {"type": "library", "name": "flask", "version": "2.3.0"},
        {"type": "library", "name": "requests", "version": "2.28.0"},
    ],
}

SAMPLE_JUNIT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<testsuites name="unit-tests" tests="10" failures="1" errors="0">'
    '<testsuite name="auth" tests="5" failures="0">'
    '<testcase name="test_login" classname="auth"/>'
    '<testcase name="test_logout" classname="auth"/>'
    '<testcase name="test_token" classname="auth"/>'
    '<testcase name="test_refresh" classname="auth"/>'
    '<testcase name="test_revoke" classname="auth"/>'
    '</testsuite>'
    '<testsuite name="api" tests="5" failures="1">'
    '<testcase name="test_get" classname="api"/>'
    '<testcase name="test_post" classname="api"/>'
    '<testcase name="test_put" classname="api"/>'
    '<testcase name="test_delete" classname="api"/>'
    '<testcase name="test_patch" classname="api">'
    '<failure type="assertion" message="Expected 200 got 500"/>'
    '</testcase>'
    '</testsuite>'
    '</testsuites>'
)


class TestImport:
    def test_import_sarif(self, multi_repo_client):
        r = multi_repo_client.post("/import-sarif", json={
            "sarif": SAMPLE_SARIF,
            "framework": "eu-ai-act",
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("findings_count", 0) >= 0

    def test_import_sbom(self, multi_repo_client):
        r = multi_repo_client.post("/import-sbom", json={
            "sbom": SAMPLE_SBOM,
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("components_count", 0) >= 0

    def test_import_junit(self, multi_repo_client):
        r = multi_repo_client.post("/import-junit", json={
            "junit_xml": SAMPLE_JUNIT,
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("total_tests", 0) >= 0
