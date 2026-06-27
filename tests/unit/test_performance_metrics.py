from src.domain.performance_metrics import PerformanceMetrics


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_generation_metrics_counters_update_correctly():
    clock = _FakeClock()
    metrics = PerformanceMetrics(clock)

    metrics.start_generation(batch_size=5000)
    clock.advance(1.25)
    snapshot = metrics.finish_generation(
        total_generated_schedules=42,
        schedules_stored_sqlite=42,
        domain_prunes=3,
        threshold_rejections=4,
        forward_checking_rejections=5,
        sqlite_stored_row_count=42,
    )

    assert snapshot.generation_seconds == 1.25
    assert snapshot.total_generated_schedules == 42
    assert snapshot.schedules_stored_sqlite == 42
    assert snapshot.domain_prunes == 3
    assert snapshot.threshold_rejections == 4
    assert snapshot.forward_checking_rejections == 5
    assert snapshot.sqlite_stored_row_count == 42
    assert snapshot.active_batch_size == 5000


def test_generation_metrics_reset_between_runs():
    clock = _FakeClock()
    metrics = PerformanceMetrics(clock)

    metrics.start_generation(batch_size=5000)
    clock.advance(1.0)
    metrics.finish_generation(total_generated_schedules=10, domain_prunes=2)

    metrics.start_generation(batch_size=5000)
    snapshot = metrics.snapshot()

    assert snapshot.total_generated_schedules == 0
    assert snapshot.domain_prunes == 0
    assert snapshot.active_batch_size == 5000


def test_ranking_and_loading_metrics_record_durations():
    clock = _FakeClock()
    metrics = PerformanceMetrics(clock)

    metrics.start_ranking()
    clock.advance(0.5)
    ranking_snapshot = metrics.finish_ranking()

    metrics.start_load_batch(batch_size=5000, auto_load=False)
    clock.advance(0.25)
    load_snapshot = metrics.finish_load_batch(sqlite_stored_row_count=123)

    metrics.start_load_batch(batch_size=5000, auto_load=True)
    clock.advance(0.75)
    auto_snapshot = metrics.finish_load_batch(sqlite_stored_row_count=456)

    assert ranking_snapshot.ranking_seconds == 0.5
    assert load_snapshot.load_more_batch_seconds == 0.25
    assert load_snapshot.sqlite_stored_row_count == 123
    assert auto_snapshot.auto_load_batch_seconds == 0.75
    assert auto_snapshot.sqlite_stored_row_count == 456
