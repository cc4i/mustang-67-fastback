"""Verify < 20 ms VL53L1X reflex brake, ToF I2C fault fail-closed interlock, and 100 ms Deadman Watchdog."""

from __future__ import annotations

from mustang_ai.config import RadxaPinConfig
from mustang_ai.hal.drive_actuators import SimDriveActuator
from mustang_ai.hal.rangefinder_vl53l1x import SimRangefinder
from mustang_ai.protocol.messages import ControlIntent
from mustang_ai.runtime.state_bus import StateBus
from mustang_ai.runtime.watchdog_reflex import WatchdogReflexGovernor


def test_forward_obstacle_reflex_brake_under_120mm(
    pins: RadxaPinConfig,
    state_bus: StateBus,
    sim_tof: SimRangefinder,
    sim_actuator: SimDriveActuator,
) -> None:
    gov = WatchdogReflexGovernor(rangefinder=sim_tof, actuators=sim_actuator, bus=state_bus, pins=pins)
    t0 = 100.0
    state_bus.publish_intent(
        ControlIntent(
            timestamp_s=t0,
            source_mode="MANEUVER",
            desired_throttle=0.70,
            desired_steering_deg=5.0,
        )
    )
    # 1. Clear path (600 mm): forward drive permitted
    sim_tof.set_distance_mm(600, valid=True)
    cmd_clear = gov.step_once(now_s=t0 + 0.010)
    assert cmd_clear.emergency_brake is False
    assert cmd_clear.motor_in1_duty == 0.70

    # 2. Obstacle at 95 mm (< 120 mm threshold): immediate short-brake override
    sim_tof.set_distance_mm(95, valid=True)
    cmd_stop = gov.step_once(now_s=t0 + 0.020)
    assert cmd_stop.emergency_brake is True
    assert cmd_stop.motor_in1_duty == 1.0
    assert cmd_stop.motor_in2_duty == 1.0
    assert gov.reflex_brake_count == 1

    # 3. Reversing (desired_throttle < 0) while at 95 mm MUST remain permitted so car can back out
    state_bus.publish_intent(
        ControlIntent(
            timestamp_s=t0 + 0.025,
            source_mode="EVASIVE_BYPASS",
            desired_throttle=-0.40,
            desired_steering_deg=0.0,
        )
    )
    cmd_rev = gov.step_once(now_s=t0 + 0.030)
    assert cmd_rev.emergency_brake is False
    assert cmd_rev.motor_in1_duty == 0.0
    assert cmd_rev.motor_in2_duty == 0.40


def test_tof_sensor_fault_triggers_fail_closed_brake(
    pins: RadxaPinConfig,
    state_bus: StateBus,
    sim_tof: SimRangefinder,
    sim_actuator: SimDriveActuator,
) -> None:
    gov = WatchdogReflexGovernor(rangefinder=sim_tof, actuators=sim_actuator, bus=state_bus, pins=pins)
    t0 = 200.0
    state_bus.publish_intent(
        ControlIntent(
            timestamp_s=t0,
            source_mode="MANUAL_TOOL",
            desired_throttle=0.50,
            desired_steering_deg=0.0,
        )
    )
    sim_tof.set_distance_mm(9999, valid=False)
    cmd = gov.step_once(now_s=t0 + 0.010)
    assert cmd.emergency_brake is True
    assert cmd.override_reason == "TOF_SENSOR_FAULT"


def test_100ms_deadman_watchdog_trip_and_recovery(
    pins: RadxaPinConfig,
    state_bus: StateBus,
    sim_tof: SimRangefinder,
    sim_actuator: SimDriveActuator,
) -> None:
    gov = WatchdogReflexGovernor(rangefinder=sim_tof, actuators=sim_actuator, bus=state_bus, pins=pins)
    sim_tof.set_distance_mm(900, valid=True)
    t0 = 500.0

    state_bus.publish_intent(
        ControlIntent(
            timestamp_s=t0,
            source_mode="FOLLOW_PERSON",
            desired_throttle=0.60,
            desired_steering_deg=8.0,
        )
    )
    # At +80 ms (< 100 ms): still valid
    cmd_ok = gov.step_once(now_s=t0 + 0.080)
    assert cmd_ok.watchdog_tripped is False
    assert cmd_ok.emergency_brake is False
    assert cmd_ok.motor_in1_duty == 0.60

    # At +105 ms (> 100 ms): Deadman Watchdog trips -> short-brake + center steering
    cmd_tripped = gov.step_once(now_s=t0 + 0.105)
    assert cmd_tripped.watchdog_tripped is True
    assert cmd_tripped.emergency_brake is True
    assert cmd_tripped.servo_pulse_us == pins.servo_center_pulse_us
    assert gov.watchdog_trip_count == 1

    # Fresh intent published at +120 ms recovers drive immediately
    state_bus.publish_intent(
        ControlIntent(
            timestamp_s=t0 + 0.120,
            source_mode="FOLLOW_PERSON",
            desired_throttle=0.45,
            desired_steering_deg=-6.0,
        )
    )
    cmd_recovered = gov.step_once(now_s=t0 + 0.130)
    assert cmd_recovered.watchdog_tripped is False
    assert cmd_recovered.emergency_brake is False
    assert cmd_recovered.motor_in1_duty == 0.45
