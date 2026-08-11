'''USART Config = 115200,8,N,1,RTU, Modbus protocol
Config station IDs = 1,2,3, total 3 devices, 4 channels per device
PV address         = 0x1000 ~ 0x1003
SensorType address = 0x1100 ~ 0x1103, 0:TC_K, 14:PT100
CJC_source address = 0x1120 ~ 0x1123, 0:Internal, 1:External, 2:HostPV4
Broadcast HostPV4  = 0x4718

Test plan
---------
Test 1:
1. Read PV channel 1~4 from station 1,2,3. All transactions shall complete
   without a Modbus exception/error response.
2. On every CJC_source channel, write/read-back values 0,1,2. They shall
   succeed and read back the same value.
3. Write CJC_source = 3. The device shall reject it with a Modbus error
   response. If value 3 is accepted, the test fails.
4. Restore the original CJC_source value after each channel test.

Test 2: station 1 test - TBD

############## above is test plan ##########################
############## below is Python code ########################
'''

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from pymodbus.client import ModbusSerialClient
from pymodbus.framer import FramerType


# -----------------------------------------------------------------------------
# Modbus configuration
# -----------------------------------------------------------------------------
DEFAULT_PORT = "COM8"
BAUDRATE = 115200
BYTESIZE = 8
PARITY = "N"
STOPBITS = 1
TIMEOUT_S = 1.0

STATION_IDS = (1, 2, 3)
CHANNEL_COUNT = 4

REG_PV_BASE = 0x1000
REG_SENSOR_TYPE_BASE = 0x1100
REG_CJC_SOURCE_BASE = 0x1120
REG_BROADCAST_HOST_PV4 = 0x4718

VALID_CJC_SOURCES = (0, 1, 2)
INVALID_CJC_SOURCE = 3


@dataclass
class TestCounter:
    passed: int = 0
    failed: int = 0

    def check(self, condition: bool, description: str) -> bool:
        if condition:
            self.passed += 1
            print(f"[PASS] {description}")
            return True

        self.failed += 1
        print(f"[FAIL] {description}")
        return False


# -----------------------------------------------------------------------------
# PyModbus compatibility helpers
# PyModbus 3.10/3.11 uses device_id; older 3.x releases used slave.
# -----------------------------------------------------------------------------
def read_holding_registers(client, address: int, count: int, station_id: int):
    try:
        return client.read_holding_registers(
            address=address,
            count=count,
            device_id=station_id,
        )
    except TypeError:
        return client.read_holding_registers(
            address=address,
            count=count,
            slave=station_id,
        )


def write_register(client, address: int, value: int, station_id: int):
    try:
        return client.write_register(
            address=address,
            value=value,
            device_id=station_id,
        )
    except TypeError:
        return client.write_register(
            address=address,
            value=value,
            slave=station_id,
        )


def response_ok(response) -> bool:
    return response is not None and not response.isError()


def read_one_register(client, station_id: int, address: int):
    response = read_holding_registers(client, address, 1, station_id)
    if not response_ok(response):
        return False, None, response

    if not getattr(response, "registers", None):
        return False, None, response

    return True, response.registers[0], response


# -----------------------------------------------------------------------------
# Test 1-A: Read PV from all three stations
# -----------------------------------------------------------------------------
def test_read_all_pv(client, counter: TestCounter) -> None:
    print("\n========== TEST 1-A: Read PV, stations 1~3 ==========")

    for station_id in STATION_IDS:
        response = read_holding_registers(
            client,
            REG_PV_BASE,
            CHANNEL_COUNT,
            station_id,
        )

        if not counter.check(
            response_ok(response),
            f"Station {station_id}: read PV 0x{REG_PV_BASE:04X}~0x{REG_PV_BASE + CHANNEL_COUNT - 1:04X}",
        ):
            print(f"       response = {response}")
            continue

        registers = getattr(response, "registers", [])
        if not counter.check(
            len(registers) == CHANNEL_COUNT,
            f"Station {station_id}: returned {CHANNEL_COUNT} PV registers",
        ):
            print(f"       registers = {registers}")
            continue

        for channel, raw_pv in enumerate(registers, start=1):
            # Display both raw value and a common 0.1-degree interpretation.
            # PASS/FAIL is based only on Modbus communication, per the test plan.
            signed_pv = raw_pv if raw_pv < 0x8000 else raw_pv - 0x10000
            print(
                f"       Station {station_id} CH{channel}: "
                f"raw=0x{raw_pv:04X} ({signed_pv}), temp={signed_pv / 10.0:.1f}"
            )

        time.sleep(0.05)


# -----------------------------------------------------------------------------
# Test 1-B: CJC_source valid/invalid range test
# -----------------------------------------------------------------------------
def test_cjc_source(client, counter: TestCounter) -> None:
    print("\n========== TEST 1-B: CJC_source 0/1/2 valid, 3 invalid ==========")

    for station_id in STATION_IDS:
        print(f"\n--- Station {station_id} ---")

        for channel in range(CHANNEL_COUNT):
            address = REG_CJC_SOURCE_BASE + channel
            channel_no = channel + 1

            ok, original_value, response = read_one_register(
                client,
                station_id,
                address,
            )

            if not counter.check(
                ok,
                f"Station {station_id} CH{channel_no}: read original CJC_source",
            ):
                print(f"       response = {response}")
                continue

            print(f"       original CJC_source = {original_value}")

            try:
                # Valid values: write shall succeed and read-back shall match.
                for test_value in VALID_CJC_SOURCES:
                    write_response = write_register(
                        client,
                        address,
                        test_value,
                        station_id,
                    )

                    write_ok = counter.check(
                        response_ok(write_response),
                        f"Station {station_id} CH{channel_no}: write CJC_source={test_value}",
                    )

                    if write_ok:
                        read_ok, readback, read_response = read_one_register(
                            client,
                            station_id,
                            address,
                        )

                        if counter.check(
                            read_ok,
                            f"Station {station_id} CH{channel_no}: read-back CJC_source={test_value}",
                        ):
                            counter.check(
                                readback == test_value,
                                f"Station {station_id} CH{channel_no}: verify CJC_source={test_value}, read={readback}",
                            )
                        else:
                            print(f"       response = {read_response}")
                    else:
                        print(f"       response = {write_response}")

                    time.sleep(0.05)

                # Invalid value: write is expected to return a Modbus exception.
                invalid_response = write_register(
                    client,
                    address,
                    INVALID_CJC_SOURCE,
                    station_id,
                )

                counter.check(
                    not response_ok(invalid_response),
                    f"Station {station_id} CH{channel_no}: CJC_source=3 is rejected",
                )

                if response_ok(invalid_response):
                    ok_after, value_after, _ = read_one_register(
                        client,
                        station_id,
                        address,
                    )
                    if ok_after:
                        print(
                            f"       WARNING: invalid write succeeded; "
                            f"register now reads {value_after}"
                        )
                else:
                    print(f"       expected rejection response = {invalid_response}")

            finally:
                # Restore original configuration even if an intermediate test fails.
                restore_response = write_register(
                    client,
                    address,
                    original_value,
                    station_id,
                )
                restore_write_ok = response_ok(restore_response)

                if restore_write_ok:
                    restore_read_ok, restored_value, _ = read_one_register(
                        client,
                        station_id,
                        address,
                    )
                    restore_ok = restore_read_ok and restored_value == original_value
                else:
                    restore_ok = False

                counter.check(
                    restore_ok,
                    f"Station {station_id} CH{channel_no}: restore CJC_source={original_value}",
                )

            time.sleep(0.05)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="USART/Modbus RTU automatic test for 3 x 4-channel devices"
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Serial port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=TIMEOUT_S,
        help=f"Modbus timeout in seconds (default: {TIMEOUT_S})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("====================================================")
    print(" Modbus RTU Test")
    print("====================================================")
    print(f"Port       : {args.port}")
    print(f"USART      : {BAUDRATE}, {BYTESIZE}, {PARITY}, {STOPBITS}")
    print(f"Stations   : {STATION_IDS}")
    print(f"PV         : 0x{REG_PV_BASE:04X}~0x{REG_PV_BASE + 3:04X}")
    print(f"CJC_source : 0x{REG_CJC_SOURCE_BASE:04X}~0x{REG_CJC_SOURCE_BASE + 3:04X}")

    client = ModbusSerialClient(
        port=args.port,
        framer=FramerType.RTU,
        baudrate=BAUDRATE,
        bytesize=BYTESIZE,
        parity=PARITY,
        stopbits=STOPBITS,
        timeout=args.timeout,
    )

    counter = TestCounter()

    try:
        if not client.connect():
            print(f"\n[FATAL] Cannot open/connect Modbus port: {args.port}")
            return 2

        print("\n[INFO] Modbus connected")

        test_read_all_pv(client, counter)
        test_cjc_source(client, counter)

    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
        return 130
    except Exception as exc:
        print(f"\n[FATAL] Unexpected exception: {type(exc).__name__}: {exc}")
        return 2
    finally:
        client.close()

    total = counter.passed + counter.failed

    print("\n====================================================")
    print(" TEST SUMMARY")
    print("====================================================")
    print(f"Total : {total}")
    print(f"PASS  : {counter.passed}")
    print(f"FAIL  : {counter.failed}")

    if counter.failed == 0:
        print("RESULT: PASS")
        return 0

    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
