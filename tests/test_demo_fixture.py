def test_demo_crash_fixture():
    from self_healer.heuristics import diagnose_heuristic, parse_logs_heuristic

    logs = open("fixtures/demo_captured/sample_crash.log").read()
    parsed = parse_logs_heuristic(logs)
    diagnosis = diagnose_heuristic(parsed)
    assert parsed.source.value in ("systemd", "mixed")
    assert diagnosis.failure_category == "service_failure"
    assert diagnosis.confidence >= 0.7
