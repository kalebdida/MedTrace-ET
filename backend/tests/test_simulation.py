from evaluation.simulate import evaluate, generate


def test_generation_is_reproducible_and_labelled():
    journeys, scenario = generate(serials=200, clone_rate=0.2, seed=7)
    again, _ = generate(serials=200, clone_rate=0.2, seed=7)
    assert [s.obs.event_id for s in journeys["SN000150"]] == [s.obs.event_id for s in again["SN000150"]]
    assert set(scenario.values()) == {"genuine", "other_city", "same_city"}
    for serial, scans in journeys.items():
        times = [s.obs.scanned_at for s in scans]
        assert times == sorted(times)
        assert any(s.is_clone for s in scans) == (scenario[serial] != "genuine")


def test_evaluation_produces_rates_and_feature_rows():
    journeys, scenario = generate(serials=300, clone_rate=0.2, seed=11)
    rows = []
    result = evaluate(journeys, scenario, max_speed_kmh=120, rows=rows)
    assert len(rows) == sum(len(v) for v in journeys.values())
    assert result["detected"] > 0.5
    assert result["false_alarm_rate"] < 0.05
    assert {"max_speed_kmh", "prior_scans", "is_clone_scan", "serial_cloned"} <= set(rows[0])
