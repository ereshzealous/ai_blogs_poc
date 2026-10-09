import pytest

from simulated_enterprise.world import BusinessError


def test_seeded_incident_and_running_release(world):
    assert world.get_incident("INC-4917")["service"] == "checkout-api"
    assert world.running("checkout-api", "production") == "rel-2031"
    assert not world.healthy()


def test_rollback_recovers_after_the_recovery_window(world):
    world.rollback_release("checkout-api", "production", "rel-2030")
    assert world.running("checkout-api", "production") == "rel-2030"
    assert world.query_metrics("checkout-api", "production", "latency_p95_ms", 3)["max"] < 400
    assert world.healthy()


def test_same_key_same_args_is_replayed_not_executed(world):
    a = world.rollback_release("checkout-api", "production", "rel-2030", key="k1")
    b = world.rollback_release("checkout-api", "production", "rel-2030", key="k1")
    assert b["idempotent_replay"] and a["to_release"] == b["to_release"]
    assert len(world.executions("rollback_release")) == 1 and world.replays("rollback_release") == 1


def test_same_key_different_args_is_refused(world):
    world.rollback_release("checkout-api", "production", "rel-2030", key="k1")
    with pytest.raises(BusinessError):
        world.rollback_release("checkout-api", "production", "rel-2029", key="k1")


def test_no_key_executes_every_time(world):
    world.rollback_release("checkout-api", "production", "rel-2030")
    world.rollback_release("checkout-api", "production", "rel-2030")
    assert len(world.executions("rollback_release")) == 2


def test_rollback_target_must_be_a_release_of_that_service(world):
    with pytest.raises(BusinessError):
        world.rollback_release("checkout-api", "production", "rel-7709")


def test_faults_fire_the_armed_number_of_times(world):
    world.arm_fault("rollback_release", "lose_response", 8, 1)
    assert world.take_fault("rollback_release") == ("lose_response", 8)
    assert world.take_fault("rollback_release") is None
