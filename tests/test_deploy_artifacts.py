from scripts.validate_deploy_artifacts import validate_deploy_artifacts


def test_deploy_artifacts_are_isolated_and_complete():
    report = validate_deploy_artifacts()

    assert report["ok"] is True, report["issues"]
