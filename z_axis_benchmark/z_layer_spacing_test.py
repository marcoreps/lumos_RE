#!/usr/bin/env python3

"""
Lumos Ultra Z layer-spacing metrology
======================================

Purpose
-------
Measure the ACTUAL physical spacing between many consecutive small Z
increments using a Parker MX80L analog Sin/Cos encoder connected to a
TMC4671 evaluation board.

This test is intended to emulate the Z-layer progression used during
volumetric glass engraving.

Questions this experiment can answer:

    - Is a commanded 20 um layer really 20 um physically?
    - How much does individual layer spacing vary?
    - Is the variation periodic with absolute Z position?
    - Does the same spatial error waveform repeat on a second pass?
    - Is there a ~160-170 um repeating pattern?
    - Is cumulative Z scale slightly wrong?

IMPORTANT
---------
- Parker motor is NEVER energized.
- Parker/TMC4671 is used only as an external encoder.
- No homing commands are issued.
- Bulk repositioning uses ordinary multi-mm Lumos moves.
- Measurement region is traversed in ONE direction only.
- Each individual layer command is the configured layer pitch.
- Every measurement waits for Parker-confirmed mechanical settling.
- Nothing automatically returns after Ctrl-C or an error.

Default experiment
------------------
Two forward passes over 5 mm with 20 um layer spacing:

    python z_layer_spacing_test.py

Explicit equivalent:

    python z_layer_spacing_test.py \
        --pitch-um 20 \
        --span-mm 5 \
        --passes 2 \
        --direction positive

Negative direction:

    python z_layer_spacing_test.py \
        --direction negative

Faster/slower precision motion:

    python z_layer_spacing_test.py \
        --feed 60 \
        --reposition-feed 600

Output
------
logs/
└── layer_spacing_YYYYMMDD_HHMMSS/
    ├── metadata.csv
    ├── moves.csv
    ├── layers.csv
    ├── encoder_samples.csv
    └── summary.csv

"""

import argparse
import csv
import json
import math
import os
import platform
import re
import statistics
import sys
import time

from collections import deque
from datetime import datetime
from importlib.metadata import (
    PackageNotFoundError,
    version as package_version,
)

from pytrinamic.connections import ConnectionManager
from pytrinamic.evalboards import TMC4671_eval
from pytrinamic.ic import TMC4671

from query_mcu import (
    DEFAULT_IP,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    send_mcu_command,
)


# ======================================================================
# Version
# ======================================================================

SCRIPT_VERSION = "2026-09-25.1-layer-spacing"


# ======================================================================
# Parker MX80L / TMC4671 configuration
# ======================================================================

ENCODER_PITCH_UM = 20.0
COUNTS_PER_PITCH = 65536.0

UM_PER_COUNT = (
    ENCODER_PITCH_UM
    / COUNTS_PER_PITCH
)

AENC_SAFE_START = 0x40008000
AENC_PPR = 635

AENC_0_SCALE = 256
AENC_0_OFFSET = 33475

AENC_1_SCALE = 256
AENC_1_OFFSET = 33611

AENC_2_SCALE = 256
AENC_2_OFFSET = 33009


# ======================================================================
# Conservative limits for this experiment
# ======================================================================

MAX_SPAN_MM = 10.0
MAX_PRELOAD_MM = 1.0

MAX_REPOSITION_FEED_MM_MIN = 1200.0
MAX_MEASUREMENT_FEED_MM_MIN = 300.0

# A multi-mm reposition should certainly cause physical movement.
BULK_MIN_CHECK_MOVE_MM = 0.500
BULK_MIN_FOLLOW_FRACTION = 0.50


# ======================================================================
# Helpers
# ======================================================================

M27_Z_RE = re.compile(
    r"\bZ\s*(-?\d+(?:\.\d+)?)"
)


def now_iso():
    return (
        datetime.now()
        .astimezone()
        .isoformat()
    )


def u32(value):
    return int(value) & 0xFFFFFFFF


def signed_delta_u32(a, b):

    delta = (
        u32(a) - u32(b)
    ) & 0xFFFFFFFF

    if delta & 0x80000000:
        delta -= 0x100000000

    return delta


def delta_um(a, b):

    return (
        signed_delta_u32(a, b)
        * UM_PER_COUNT
    )


def package_ver(name):

    try:
        return package_version(name)

    except PackageNotFoundError:
        return "unknown"


def rms(values):

    values = list(values)

    if not values:
        return float("nan")

    return math.sqrt(
        sum(x * x for x in values)
        / len(values)
    )


def pearson_correlation(a, b):

    a = list(a)
    b = list(b)

    if (
        len(a) != len(b)
        or len(a) < 2
    ):
        return float("nan")

    ma = statistics.mean(a)
    mb = statistics.mean(b)

    da = [
        x - ma
        for x in a
    ]

    db = [
        x - mb
        for x in b
    ]

    denominator = math.sqrt(
        sum(x * x for x in da)
        *
        sum(x * x for x in db)
    )

    if denominator == 0:
        return float("nan")

    return (
        sum(
            x * y
            for x, y in zip(da, db)
        )
        / denominator
    )


# ======================================================================
# Lumos MCU communication
# ======================================================================

def send_command(
    command,
    *,
    ip,
    port,
    timeout,
):

    return send_mcu_command(
        command,
        ip=ip,
        port=port,
        timeout=timeout,
    )


def query_lumos_z(
    *,
    ip,
    port,
    timeout,
):

    result = send_command(
        "M27",
        ip=ip,
        port=port,
        timeout=timeout,
    )

    raw = str(
        result.get(
            "data",
            "",
        )
    )

    match = (
        M27_Z_RE.search(
            raw
        )
    )

    if not match:

        raise RuntimeError(
            "Could not parse Lumos Z "
            f"from M27 response: {raw!r}"
        )

    return (
        float(
            match.group(1)
        ),
        raw,
        result,
    )


# ======================================================================
# TMC4671 encoder configuration
# ======================================================================

def configure_encoder_only(mc):
    """
    Configure ONLY the TMC4671 analog encoder.

    The Parker motor is never energized.
    """

    mc.write_register(
        TMC4671.REG.MODE_RAMP_MODE_MOTION,
        TMC4671.ENUM.MOTION_MODE_STOPPED,
    )

    mc.write_register_field(
        TMC4671.FIELD.UD_EXT,
        0,
    )

    mc.write_register_field(
        TMC4671.FIELD.UQ_EXT,
        0,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_DECODER_COUNT,
        AENC_SAFE_START,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_DECODER_MODE_120DEG_N90DEG,
        0,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_DECODER_PPR,
        AENC_PPR,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_0_SCALE,
        AENC_0_SCALE,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_0_OFFSET,
        AENC_0_OFFSET,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_1_SCALE,
        AENC_1_SCALE,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_1_OFFSET,
        AENC_1_OFFSET,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_2_SCALE,
        AENC_2_SCALE,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_2_OFFSET,
        AENC_2_OFFSET,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_0_SELECT,
        0,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_1_SELECT,
        1,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_2_SELECT,
        2,
    )

    mc.write_register_field(
        TMC4671.FIELD.AENC_DECODER_PHI_A_OFFSET,
        0,
    )

    time.sleep(0.25)


def read_encoder(mc):

    return u32(
        mc.read_register(
            TMC4671.REG.AENC_DECODER_COUNT
        )
    )


# ======================================================================
# Encoder measurement
# ======================================================================

def measure_encoder(
    mc,
    *,
    duration_s,
    interval_s=0.002,
):

    raw_counts = []
    raw_times = []

    start = time.monotonic()
    deadline = start + duration_s

    while (
        time.monotonic()
        < deadline
    ):

        t = time.monotonic()

        raw_counts.append(
            read_encoder(mc)
        )

        raw_times.append(
            t - start
        )

        time.sleep(
            interval_s
        )

    if not raw_counts:

        raise RuntimeError(
            "No encoder samples acquired"
        )

    center = int(
        round(
            statistics.median(
                raw_counts
            )
        )
    )

    deviations = [
        delta_um(
            count,
            center,
        )
        for count in raw_counts
    ]

    std_um = (
        statistics.pstdev(
            deviations
        )
        if len(deviations) > 1
        else 0.0
    )

    pp_um = (
        max(deviations)
        - min(deviations)
    )

    return {
        "count":
            center,

        "std_um":
            std_um,

        "pp_um":
            pp_um,

        "samples":
            len(raw_counts),

        "raw_counts":
            raw_counts,

        "raw_times":
            raw_times,

        "start_monotonic":
            start,
    }


# ======================================================================
# Encoder-confirmed settling
# ======================================================================

def wait_for_encoder_stable(
    mc,
    *,
    guard_s,
    stable_time_s,
    threshold_um,
    poll_s=0.010,
    timeout_s=5.0,
):

    start = time.monotonic()

    # --------------------------------------------------------------
    # Guard
    # --------------------------------------------------------------

    while (
        time.monotonic() - start
        < guard_s
    ):

        read_encoder(mc)

        time.sleep(
            poll_s
        )

    # --------------------------------------------------------------
    # Stability interval
    # --------------------------------------------------------------

    history = deque()

    while True:

        now = time.monotonic()

        count = read_encoder(
            mc
        )

        history.append(
            (now, count)
        )

        while (
            history
            and (
                now
                - history[0][0]
            ) > stable_time_s
        ):

            history.popleft()

        if len(history) >= 2:

            age = (
                now
                - history[0][0]
            )

            if (
                age
                >= stable_time_s * 0.95
            ):

                reference = (
                    history[0][1]
                )

                values_um = [
                    delta_um(
                        count,
                        reference,
                    )
                    for _, count
                    in history
                ]

                span_um = (
                    max(values_um)
                    - min(values_um)
                )

                if (
                    span_um
                    <= threshold_um
                ):

                    return {
                        "settle_total_s":
                            now - start,

                        "stable_time_s":
                            age,

                        "stable_span_um":
                            span_um,

                        "stable_samples":
                            len(history),
                    }

        if (
            now - start
            > timeout_s
        ):

            raise RuntimeError(
                "Z failed to become "
                "encoder-stable within "
                f"{timeout_s:.1f} s"
            )

        time.sleep(
            poll_s
        )


# ======================================================================
# Logger
# ======================================================================

class Logger:

    def __init__(
        self,
        run_dir,
    ):

        self.run_dir = run_dir

        self.run_start = (
            time.monotonic()
        )

        # ----------------------------------------------------------
        # Metadata
        # ----------------------------------------------------------

        self.metadata_file = open(
            run_dir / "metadata.csv",
            "w",
            newline="",
        )

        self.metadata_csv = csv.writer(
            self.metadata_file
        )

        self.metadata_csv.writerow([
            "key",
            "value",
        ])

        # ----------------------------------------------------------
        # Moves
        # ----------------------------------------------------------

        self.moves_file = open(
            run_dir / "moves.csv",
            "w",
            newline="",
        )

        self.moves_csv = csv.writer(
            self.moves_file
        )

        self.moves_csv.writerow([
            "timestamp",
            "elapsed_s",

            "pass",
            "phase",

            "from_z_mm",
            "to_z_mm",
            "command_delta_um",

            "feed_mm_min",

            "encoder_before",
            "encoder_after",
            "encoder_delta_um",

            "gcode",
        ])

        # ----------------------------------------------------------
        # Layers
        # ----------------------------------------------------------

        self.layers_file = open(
            run_dir / "layers.csv",
            "w",
            newline="",
        )

        self.layers_csv = csv.writer(
            self.layers_file
        )

        self.layers_csv.writerow([
            "pass",
            "layer_index",

            "timestamp",
            "elapsed_s",

            "commanded_z_mm",
            "commanded_from_pass_start_um",

            "m27_z_mm",
            "m27_raw",

            "encoder_count",
            "encoder_relative_to_run_zero_um",

            "physical_position_um",
            "physical_from_pass_start_um",

            "physical_step_signed_um",
            "physical_spacing_um",

            "commanded_spacing_um",
            "step_error_um",

            "cumulative_position_error_um",

            "encoder_std_um",
            "encoder_pp_um",

            "settle_total_s",
            "stable_span_um",
        ])

        # ----------------------------------------------------------
        # Raw samples
        # ----------------------------------------------------------

        self.samples_file = open(
            run_dir / "encoder_samples.csv",
            "w",
            newline="",
        )

        self.samples_csv = csv.writer(
            self.samples_file
        )

        self.samples_csv.writerow([
            "pass",
            "layer_index",

            "sample_index",

            "run_elapsed_s",
            "measurement_elapsed_s",

            "encoder_count",
            "encoder_relative_to_run_zero_um",
        ])

        self.summary_file = None
        self.summary_csv = None

    # ------------------------------------------------------------------

    def elapsed(self):

        return (
            time.monotonic()
            - self.run_start
        )

    # ------------------------------------------------------------------

    def metadata(
        self,
        key,
        value,
    ):

        self.metadata_csv.writerow([
            key,
            value,
        ])

        self.metadata_file.flush()

    # ------------------------------------------------------------------

    def move(
        self,
        *,
        pass_index,
        phase,

        from_z,
        to_z,

        feed,

        encoder_before,
        encoder_after,

        gcode,
    ):

        self.moves_csv.writerow([
            now_iso(),
            self.elapsed(),

            pass_index,
            phase,

            from_z,
            to_z,

            (
                to_z - from_z
            ) * 1000.0,

            feed,

            encoder_before,
            encoder_after,

            delta_um(
                encoder_after,
                encoder_before,
            ),

            gcode,
        ])

        self.moves_file.flush()

    # ------------------------------------------------------------------

    def layer(
        self,
        *,
        pass_index,
        layer_index,

        commanded_z_mm,
        commanded_from_start_um,

        m27_z_mm,
        m27_raw,

        measurement,

        run_zero_count,

        physical_position_um,
        physical_from_start_um,

        physical_step_signed_um,
        physical_spacing_um,

        commanded_spacing_um,
        step_error_um,

        cumulative_position_error_um,

        settling,
    ):

        self.layers_csv.writerow([
            pass_index,
            layer_index,

            now_iso(),
            self.elapsed(),

            commanded_z_mm,
            commanded_from_start_um,

            m27_z_mm,
            m27_raw,

            measurement["count"],

            delta_um(
                measurement["count"],
                run_zero_count,
            ),

            physical_position_um,
            physical_from_start_um,

            physical_step_signed_um,
            physical_spacing_um,

            commanded_spacing_um,
            step_error_um,

            cumulative_position_error_um,

            measurement["std_um"],
            measurement["pp_um"],

            settling[
                "settle_total_s"
            ],

            settling[
                "stable_span_um"
            ],
        ])

        for (
            sample_index,
            (
                sample_time,
                count,
            ),
        ) in enumerate(
            zip(
                measurement["raw_times"],
                measurement["raw_counts"],
            )
        ):

            run_elapsed = (
                measurement[
                    "start_monotonic"
                ]
                + sample_time
                - self.run_start
            )

            self.samples_csv.writerow([
                pass_index,
                layer_index,

                sample_index,

                run_elapsed,
                sample_time,

                count,

                delta_um(
                    count,
                    run_zero_count,
                ),
            ])

        self.layers_file.flush()
        self.samples_file.flush()

    # ------------------------------------------------------------------

    def write_summary(
        self,
        summary_rows,
    ):

        path = (
            self.run_dir
            / "summary.csv"
        )

        with open(
            path,
            "w",
            newline="",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "metric",
                    "value",
                    "unit",
                ],
            )

            writer.writeheader()

            for row in summary_rows:

                writer.writerow(
                    row
                )

    # ------------------------------------------------------------------

    def close(self):

        for f in (
            self.metadata_file,
            self.moves_file,
            self.layers_file,
            self.samples_file,
        ):

            try:

                f.flush()
                f.close()

            except Exception:

                pass


# ======================================================================
# Experiment controller
# ======================================================================

class Experiment:

    def __init__(
        self,
        *,
        mc,
        logger,

        args,

        run_zero_count,
        initial_z,
    ):

        self.mc = mc
        self.logger = logger
        self.args = args

        self.run_zero_count = (
            run_zero_count
        )

        self.initial_z = (
            initial_z
        )

        self.current_z = (
            initial_z
        )

        # Automatically inferred from first substantial movement.
        #
        # physical_position_um =
        #     encoder_sign * raw encoder displacement
        #
        # so increasing Lumos commanded Z becomes positive physical Z.
        self.encoder_sign = None

        self.pass_step_errors = {}

    # ==================================================================
    # Common motion primitive
    # ==================================================================

    def move_absolute(
        self,
        target_z,
        *,
        feed,
        pass_index,
        phase,
        verify_bulk=False,
    ):

        from_z = (
            self.current_z
        )

        command_delta_mm = (
            target_z - from_z
        )

        if (
            abs(command_delta_mm)
            < 0.0000005
        ):

            return None

        encoder_before = (
            read_encoder(
                self.mc
            )
        )

        gcode = (
            f"G1 Z{target_z:.6f} "
            f"F{feed:.3f}"
        )

        send_command(
            gcode,

            ip=self.args.ip,
            port=self.args.port,
            timeout=self.args.timeout,
        )

        travel_time = (
            abs(command_delta_mm)
            / (
                feed / 60.0
            )
        )

        time.sleep(
            travel_time
            + 0.050
        )

        settling = (
            wait_for_encoder_stable(
                self.mc,

                guard_s=(
                    self.args.settle_guard
                ),

                stable_time_s=(
                    self.args.settle_time
                ),

                threshold_um=(
                    self.args.settle_threshold
                ),

                timeout_s=(
                    self.args.settle_timeout
                ),
            )
        )

        encoder_after = (
            read_encoder(
                self.mc
            )
        )

        encoder_delta = (
            delta_um(
                encoder_after,
                encoder_before,
            )
        )

        commanded_delta_um = (
            command_delta_mm
            * 1000.0
        )

        # ----------------------------------------------------------
        # Determine encoder polarity from first substantial move
        # ----------------------------------------------------------

        if (
            self.encoder_sign is None
            and abs(
                commanded_delta_um
            ) > 100
            and abs(
                encoder_delta
            ) > 100
        ):

            if (
                commanded_delta_um
                * encoder_delta
                >= 0
            ):

                self.encoder_sign = +1.0

            else:

                self.encoder_sign = -1.0

            print(
                "Detected encoder orientation: "
                f"{self.encoder_sign:+.0f}"
            )

        # ----------------------------------------------------------
        # Gross following check on bulk moves
        # ----------------------------------------------------------

        if (
            verify_bulk
            and abs(
                command_delta_mm
            ) >= BULK_MIN_CHECK_MOVE_MM
        ):

            actual_um = abs(
                encoder_delta
            )

            expected_um = abs(
                commanded_delta_um
            )

            fraction = (
                actual_um
                / expected_um
            )

            if (
                fraction
                < BULK_MIN_FOLLOW_FRACTION
            ):

                raise RuntimeError(
                    "ABORT: bulk Z relocation "
                    "did not produce enough "
                    "external encoder movement. "
                    f"Commanded {expected_um:.1f} um, "
                    f"Parker observed {actual_um:.1f} um. "
                    "Possible hard stop or mechanical "
                    "disconnection."
                )

        self.logger.move(
            pass_index=pass_index,
            phase=phase,

            from_z=from_z,
            to_z=target_z,

            feed=feed,

            encoder_before=(
                encoder_before
            ),

            encoder_after=(
                encoder_after
            ),

            gcode=gcode,
        )

        self.current_z = (
            target_z
        )

        return settling

    # ==================================================================
    # Convert raw encoder position into Lumos-oriented physical Z
    # ==================================================================

    def physical_position_um(
        self,
        encoder_count,
    ):

        if (
            self.encoder_sign
            is None
        ):

            raise RuntimeError(
                "Encoder direction has not yet "
                "been established."
            )

        raw_um = (
            delta_um(
                encoder_count,
                self.run_zero_count,
            )
        )

        return (
            self.encoder_sign
            * raw_um
        )

    # ==================================================================
    # One complete same-direction pass
    # ==================================================================

    def run_pass(
        self,
        pass_index,
    ):

        args = self.args

        direction_sign = (
            +1.0
            if args.direction == "positive"
            else -1.0
        )

        half_span = (
            args.span_mm / 2.0
        )

        if direction_sign > 0:

            first_offset = (
                -half_span
            )

            last_offset = (
                +half_span
            )

            preload_offset = (
                first_offset
                - args.preload_mm
            )

        else:

            first_offset = (
                +half_span
            )

            last_offset = (
                -half_span
            )

            preload_offset = (
                first_offset
                + args.preload_mm
            )

        first_z = (
            self.initial_z
            + first_offset
        )

        preload_z = (
            self.initial_z
            + preload_offset
        )

        # ----------------------------------------------------------
        # Fast multi-mm relocation
        # ----------------------------------------------------------

        print()
        print(
            f"PASS {pass_index}: "
            f"bulk reposition to preload "
            f"{preload_offset:+.3f} mm"
        )

        self.move_absolute(
            preload_z,

            feed=(
                args.reposition_feed
            ),

            pass_index=(
                pass_index
            ),

            phase="bulk_preload",

            verify_bulk=True,
        )

        # ----------------------------------------------------------
        # Controlled same-direction approach to first layer
        # ----------------------------------------------------------

        print(
            f"PASS {pass_index}: "
            f"precision approach to "
            f"{first_offset:+.3f} mm"
        )

        self.move_absolute(
            first_z,

            feed=(
                args.feed
            ),

            pass_index=(
                pass_index
            ),

            phase="initial_precision_approach",

            verify_bulk=False,
        )

        # ----------------------------------------------------------
        # Number of intervals/layers
        # ----------------------------------------------------------

        pitch_mm = (
            args.pitch_um
            / 1000.0
        )

        intervals = int(
            round(
                args.span_mm
                / pitch_mm
            )
        )

        actual_span = (
            intervals
            * pitch_mm
        )

        if (
            abs(
                actual_span
                - args.span_mm
            )
            > 1e-9
        ):

            print(
                "NOTE: requested span adjusted "
                "slightly to exact integer number "
                "of layer intervals:"
            )

            print(
                f"  requested = "
                f"{args.span_mm:.6f} mm"
            )

            print(
                f"  actual    = "
                f"{actual_span:.6f} mm"
            )

        # ----------------------------------------------------------
        # Acquire layer 0
        # ----------------------------------------------------------

        settling = (
            wait_for_encoder_stable(
                self.mc,

                guard_s=(
                    args.settle_guard
                ),

                stable_time_s=(
                    args.settle_time
                ),

                threshold_um=(
                    args.settle_threshold
                ),

                timeout_s=(
                    args.settle_timeout
                ),
            )
        )

        measurement = (
            measure_encoder(
                self.mc,

                duration_s=(
                    args.sample_time
                ),
            )
        )

        (
            m27_z,
            m27_raw,
            _result,
        ) = query_lumos_z(
            ip=args.ip,
            port=args.port,
            timeout=args.timeout,
        )

        first_physical = (
            self.physical_position_um(
                measurement["count"]
            )
        )

        previous_physical = (
            first_physical
        )

        previous_count = (
            measurement["count"]
        )

        self.logger.layer(
            pass_index=pass_index,
            layer_index=0,

            commanded_z_mm=(
                first_z
            ),

            commanded_from_start_um=0.0,

            m27_z_mm=(
                m27_z
            ),

            m27_raw=(
                m27_raw
            ),

            measurement=(
                measurement
            ),

            run_zero_count=(
                self.run_zero_count
            ),

            physical_position_um=(
                first_physical
            ),

            physical_from_start_um=0.0,

            physical_step_signed_um="",
            physical_spacing_um="",

            commanded_spacing_um="",
            step_error_um="",

            cumulative_position_error_um=0.0,

            settling=(
                settling
            ),
        )

        print()
        print(
            f"PASS {pass_index}: "
            f"{intervals + 1} layer positions, "
            f"{args.pitch_um:.3f} um nominal pitch"
        )

        print()

        step_errors = []

        # ----------------------------------------------------------
        # Layer progression
        # ----------------------------------------------------------

        for layer_index in range(
            1,
            intervals + 1,
        ):

            commanded_from_start_um = (
                layer_index
                * args.pitch_um
            )

            target_z = (
                first_z
                + direction_sign
                * (
                    commanded_from_start_um
                    / 1000.0
                )
            )

            # ------------------------------------------------------
            # Exact engraving-like layer move
            # ------------------------------------------------------

            encoder_before_move = (
                read_encoder(
                    self.mc
                )
            )

            gcode = (
                f"G1 Z{target_z:.6f} "
                f"F{args.feed:.3f}"
            )

            send_command(
                gcode,

                ip=args.ip,
                port=args.port,
                timeout=args.timeout,
            )

            travel_time = (
                pitch_mm
                / (
                    args.feed / 60.0
                )
            )

            time.sleep(
                travel_time
                + 0.030
            )

            encoder_after_move = (
                read_encoder(
                    self.mc
                )
            )

            self.logger.move(
                pass_index=pass_index,
                phase="layer_step",

                from_z=(
                    self.current_z
                ),

                to_z=(
                    target_z
                ),

                feed=(
                    args.feed
                ),

                encoder_before=(
                    encoder_before_move
                ),

                encoder_after=(
                    encoder_after_move
                ),

                gcode=(
                    gcode
                ),
            )

            self.current_z = (
                target_z
            )

            # ------------------------------------------------------
            # Parker-confirmed settling
            # ------------------------------------------------------

            settling = (
                wait_for_encoder_stable(
                    self.mc,

                    guard_s=(
                        args.settle_guard
                    ),

                    stable_time_s=(
                        args.settle_time
                    ),

                    threshold_um=(
                        args.settle_threshold
                    ),

                    timeout_s=(
                        args.settle_timeout
                    ),
                )
            )

            # ------------------------------------------------------
            # High-quality stationary encoder burst
            # ------------------------------------------------------

            measurement = (
                measure_encoder(
                    self.mc,

                    duration_s=(
                        args.sample_time
                    ),
                )
            )

            (
                m27_z,
                m27_raw,
                _result,
            ) = query_lumos_z(
                ip=args.ip,
                port=args.port,
                timeout=args.timeout,
            )

            physical_position = (
                self.physical_position_um(
                    measurement["count"]
                )
            )

            physical_from_start = (
                direction_sign
                * (
                    physical_position
                    - first_physical
                )
            )

            physical_step_signed = (
                physical_position
                - previous_physical
            )

            physical_spacing = abs(
                physical_step_signed
            )

            step_error = (
                physical_spacing
                - args.pitch_um
            )

            cumulative_error = (
                physical_from_start
                - commanded_from_start_um
            )

            step_errors.append(
                step_error
            )

            self.logger.layer(
                pass_index=pass_index,
                layer_index=layer_index,

                commanded_z_mm=(
                    target_z
                ),

                commanded_from_start_um=(
                    commanded_from_start_um
                ),

                m27_z_mm=(
                    m27_z
                ),

                m27_raw=(
                    m27_raw
                ),

                measurement=(
                    measurement
                ),

                run_zero_count=(
                    self.run_zero_count
                ),

                physical_position_um=(
                    physical_position
                ),

                physical_from_start_um=(
                    physical_from_start
                ),

                physical_step_signed_um=(
                    physical_step_signed
                ),

                physical_spacing_um=(
                    physical_spacing
                ),

                commanded_spacing_um=(
                    args.pitch_um
                ),

                step_error_um=(
                    step_error
                ),

                cumulative_position_error_um=(
                    cumulative_error
                ),

                settling=(
                    settling
                ),
            )

            previous_physical = (
                physical_position
            )

            previous_count = (
                measurement["count"]
            )

            if (
                layer_index
                % args.print_every
                == 0
                or layer_index
                == intervals
            ):

                print(
                    f"pass={pass_index}  "
                    f"layer={layer_index:04d}/"
                    f"{intervals:04d}  "
                    f"Zrel="
                    f"{commanded_from_start_um:8.1f} um  "
                    f"spacing="
                    f"{physical_spacing:7.3f} um  "
                    f"error="
                    f"{step_error:+7.3f} um  "
                    f"cum="
                    f"{cumulative_error:+8.3f} um  "
                    f"noise="
                    f"{measurement['std_um'] * 1000:6.2f} nm"
                )

        self.pass_step_errors[
            pass_index
        ] = step_errors

        # ----------------------------------------------------------
        # Per-pass summary
        # ----------------------------------------------------------

        mean_spacing = (
            statistics.mean(
                [
                    args.pitch_um + e
                    for e in step_errors
                ]
            )
        )

        spacing_std = statistics.pstdev(
            [
                args.pitch_um + e
                for e in step_errors
            ]
        )

        min_spacing = min(
            args.pitch_um + e
            for e in step_errors
        )

        max_spacing = max(
            args.pitch_um + e
            for e in step_errors
        )

        mean_step_error = (
            statistics.mean(
                step_errors
            )
        )

        step_error_rms = (
            rms(
                step_errors
            )
        )

        commanded_travel_um = (
            intervals
            * args.pitch_um
        )

        actual_travel_um = (
            commanded_travel_um
            + sum(step_errors)
        )

        scale_error_ppm = (
            (
                actual_travel_um
                / commanded_travel_um
            )
            - 1.0
        ) * 1e6

        print()
        print(
            f"PASS {pass_index} SUMMARY"
        )

        print(
            f"  mean spacing     : "
            f"{mean_spacing:.4f} um"
        )

        print(
            f"  spacing std      : "
            f"{spacing_std:.4f} um"
        )

        print(
            f"  min spacing      : "
            f"{min_spacing:.4f} um"
        )

        print(
            f"  max spacing      : "
            f"{max_spacing:.4f} um"
        )

        print(
            f"  step error RMS   : "
            f"{step_error_rms:.4f} um"
        )

        print(
            f"  scale error      : "
            f"{scale_error_ppm:+.1f} ppm"
        )

        return {
            "pass":
                pass_index,

            "mean_spacing_um":
                mean_spacing,

            "spacing_std_um":
                spacing_std,

            "min_spacing_um":
                min_spacing,

            "max_spacing_um":
                max_spacing,

            "spacing_peak_to_peak_um":
                max_spacing - min_spacing,

            "mean_step_error_um":
                mean_step_error,

            "step_error_rms_um":
                step_error_rms,

            "scale_error_ppm":
                scale_error_ppm,
        }


# ======================================================================
# CLI
# ======================================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Measure actual layer-to-layer "
            "Z spacing using Parker MX80L "
            "external encoder metrology."
        )
    )

    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
    )

    parser.add_argument(
        "--pitch-um",
        type=float,
        default=20.0,

        help=(
            "Nominal commanded layer pitch "
            "in um (default 20)"
        ),
    )

    parser.add_argument(
        "--span-mm",
        type=float,
        default=5.0,

        help=(
            "Total measured Z span in mm "
            "(default 5)"
        ),
    )

    parser.add_argument(
        "--passes",
        type=int,
        default=2,

        help=(
            "Number of repeated same-direction "
            "passes (default 2)"
        ),
    )

    parser.add_argument(
        "--direction",
        choices=[
            "positive",
            "negative",
        ],
        default="positive",

        help=(
            "Direction of measured layer progression "
            "(default positive)"
        ),
    )

    parser.add_argument(
        "--preload-mm",
        type=float,
        default=0.300,

        help=(
            "Distance before first sample used "
            "to establish approach direction "
            "(default 0.300)"
        ),
    )

    parser.add_argument(
        "--feed",
        type=float,
        default=60.0,

        help=(
            "Layer-step feed in mm/min "
            "(default 60)"
        ),
    )

    parser.add_argument(
        "--reposition-feed",
        type=float,
        default=600.0,

        help=(
            "Fast bulk reposition feed "
            "in mm/min (default 600)"
        ),
    )

    parser.add_argument(
        "--sample-time",
        type=float,
        default=0.10,

        help=(
            "High-quality encoder burst duration "
            "per layer, seconds (default 0.10)"
        ),
    )

    parser.add_argument(
        "--settle-guard",
        type=float,
        default=0.10,

        help=(
            "Minimum post-motion guard time "
            "before stability test, seconds "
            "(default 0.10)"
        ),
    )

    parser.add_argument(
        "--settle-time",
        type=float,
        default=0.20,

        help=(
            "Required continuous encoder-stable "
            "window, seconds (default 0.20)"
        ),
    )

    parser.add_argument(
        "--settle-threshold",
        type=float,
        default=0.10,

        help=(
            "Maximum Parker motion during stable "
            "window, um p-p (default 0.10)"
        ),
    )

    parser.add_argument(
        "--settle-timeout",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--print-every",
        type=int,
        default=1,

        help=(
            "Print every Nth layer "
            "(default every layer)"
        ),
    )

    parser.add_argument(
        "--yes",
        action="store_true",

        help=(
            "Skip interactive confirmation."
        ),
    )

    return (
        parser.parse_args()
    )


# ======================================================================
# Validation
# ======================================================================

def validate_args(args):

    if (
        args.pitch_um <= 0
    ):

        raise SystemExit(
            "--pitch-um must be >0"
        )

    if (
        args.span_mm <= 0
        or args.span_mm > MAX_SPAN_MM
    ):

        raise SystemExit(
            f"--span-mm must be >0 and "
            f"<={MAX_SPAN_MM:g}"
        )

    if (
        args.preload_mm <= 0
        or args.preload_mm
        > MAX_PRELOAD_MM
    ):

        raise SystemExit(
            f"--preload-mm must be >0 and "
            f"<={MAX_PRELOAD_MM:g}"
        )

    if args.passes <= 0:

        raise SystemExit(
            "--passes must be >0"
        )

    if (
        args.feed <= 0
        or args.feed
        > MAX_MEASUREMENT_FEED_MM_MIN
    ):

        raise SystemExit(
            "Invalid --feed"
        )

    if (
        args.reposition_feed <= 0
        or args.reposition_feed
        > MAX_REPOSITION_FEED_MM_MIN
    ):

        raise SystemExit(
            "Invalid --reposition-feed"
        )

    if (
        args.sample_time <= 0
        or args.settle_time <= 0
        or args.settle_guard < 0
        or args.settle_threshold <= 0
        or args.settle_timeout <= 0
    ):

        raise SystemExit(
            "Invalid measurement/settling settings"
        )

    if (
        args.print_every <= 0
    ):

        raise SystemExit(
            "--print-every must be >0"
        )


# ======================================================================
# Main
# ======================================================================

def main():

    args = parse_args()

    validate_args(
        args
    )

    # --------------------------------------------------------------
    # Output directory
    # --------------------------------------------------------------

    os.makedirs(
        "logs",
        exist_ok=True,
    )

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    from pathlib import Path

    run_dir = Path(
        "logs"
    ) / (
        f"layer_spacing_{stamp}"
    )

    run_dir.mkdir(
        exist_ok=False
    )

    logger = Logger(
        run_dir
    )

    status = "unknown"
    error_text = ""

    experiment = None

    try:

        # ----------------------------------------------------------
        # Metadata
        # ----------------------------------------------------------

        metadata = {
            "script_version":
                SCRIPT_VERSION,

            "timestamp":
                now_iso(),

            "python_version":
                sys.version.replace(
                    "\n",
                    " ",
                ),

            "platform":
                platform.platform(),

            "pytrinamic_version":
                package_ver(
                    "pytrinamic"
                ),

            "pitch_um":
                args.pitch_um,

            "span_mm":
                args.span_mm,

            "passes":
                args.passes,

            "direction":
                args.direction,

            "preload_mm":
                args.preload_mm,

            "measurement_feed_mm_min":
                args.feed,

            "reposition_feed_mm_min":
                args.reposition_feed,

            "sample_time_s":
                args.sample_time,

            "settle_guard_s":
                args.settle_guard,

            "settle_time_s":
                args.settle_time,

            "settle_threshold_um":
                args.settle_threshold,

            "encoder_pitch_um":
                ENCODER_PITCH_UM,

            "encoder_counts_per_pitch":
                COUNTS_PER_PITCH,

            "encoder_um_per_count":
                UM_PER_COUNT,
        }

        for key, value in (
            metadata.items()
        ):

            logger.metadata(
                key,
                value,
            )

        # ----------------------------------------------------------
        # Connect
        # ----------------------------------------------------------

        print()
        print(
            "Connecting to TMC4671..."
        )

        print(
            "Parker motor will NOT be energized."
        )

        print(
            "No homing commands will be issued."
        )

        print()

        with ConnectionManager(
            "--data-rate 3000000"
        ).connect() as interface:

            mc = (
                TMC4671_eval(
                    interface
                )
            )

            configure_encoder_only(
                mc
            )

            # ------------------------------------------------------
            # Lumos current position
            # ------------------------------------------------------

            (
                initial_z,
                m27_raw,
                _result,
            ) = query_lumos_z(
                ip=args.ip,
                port=args.port,
                timeout=args.timeout,
            )

            print(
                f"M27              : "
                f"{m27_raw}"
            )

            print(
                f"Initial Lumos Z  : "
                f"{initial_z:.6f} mm"
            )

            print(
                f"Layer pitch      : "
                f"{args.pitch_um:.3f} um"
            )

            print(
                f"Measured span    : "
                f"{args.span_mm:.3f} mm"
            )

            print(
                f"Passes           : "
                f"{args.passes}"
            )

            print(
                f"Direction        : "
                f"{args.direction}"
            )

            # ------------------------------------------------------
            # Establish Parker run zero
            # ------------------------------------------------------

            print()
            print(
                "Acquiring Parker software zero..."
            )

            zero = (
                measure_encoder(
                    mc,

                    duration_s=1.0,
                )
            )

            run_zero_count = (
                zero["count"]
            )

            print(
                f"Encoder zero     : "
                f"{run_zero_count}"
            )

            print(
                f"Encoder noise    : "
                f"std="
                f"{zero['std_um'] * 1000:.2f} nm, "
                f"p-p="
                f"{zero['pp_um'] * 1000:.2f} nm"
            )

            logger.metadata(
                "initial_lumos_z_mm",
                initial_z,
            )

            logger.metadata(
                "run_zero_encoder_count",
                run_zero_count,
            )

            logger.metadata(
                "initial_encoder_std_um",
                zero["std_um"],
            )

            logger.metadata(
                "initial_encoder_pp_um",
                zero["pp_um"],
            )

            # ------------------------------------------------------
            # Experiment object
            # ------------------------------------------------------

            experiment = Experiment(
                mc=mc,
                logger=logger,

                args=args,

                run_zero_count=(
                    run_zero_count
                ),

                initial_z=(
                    initial_z
                ),
            )

            # ------------------------------------------------------
            # Confirmation before motion
            # ------------------------------------------------------

            if not args.yes:

                print()
                print(
                    "NO LUMOS MOTION HAS OCCURRED YET."
                )

                print()

                number_intervals = int(
                    round(
                        args.span_mm
                        / (
                            args.pitch_um
                            / 1000.0
                        )
                    )
                )

                print(
                    f"Each pass will contain "
                    f"{number_intervals} layer intervals."
                )

                print(
                    f"Bulk repositioning may use "
                    f"multi-mm G1 moves at "
                    f"{args.reposition_feed:g} mm/min."
                )

                print(
                    "Measurement motion itself remains "
                    "one layer pitch per command."
                )

                print()

                answer = input(
                    "Type YES to begin motion: "
                ).strip()

                if answer != "YES":

                    status = (
                        "cancelled_before_motion"
                    )

                    print(
                        "Cancelled."
                    )

                    return 0

            # ------------------------------------------------------
            # Run passes
            # ------------------------------------------------------

            pass_summaries = []

            for pass_index in range(
                1,
                args.passes + 1,
            ):

                result = (
                    experiment.run_pass(
                        pass_index
                    )
                )

                pass_summaries.append(
                    result
                )

            # ------------------------------------------------------
            # Build final summary
            # ------------------------------------------------------

            summary_rows = []

            for result in (
                pass_summaries
            ):

                pass_index = (
                    result["pass"]
                )

                for (
                    key,
                    unit,
                ) in (
                    (
                        "mean_spacing_um",
                        "um",
                    ),
                    (
                        "spacing_std_um",
                        "um",
                    ),
                    (
                        "min_spacing_um",
                        "um",
                    ),
                    (
                        "max_spacing_um",
                        "um",
                    ),
                    (
                        "spacing_peak_to_peak_um",
                        "um",
                    ),
                    (
                        "step_error_rms_um",
                        "um",
                    ),
                    (
                        "scale_error_ppm",
                        "ppm",
                    ),
                ):

                    summary_rows.append({
                        "metric":
                            (
                                f"pass_{pass_index}_"
                                f"{key}"
                            ),

                        "value":
                            result[key],

                        "unit":
                            unit,
                    })

            # ------------------------------------------------------
            # Compare repeated same-direction passes
            # ------------------------------------------------------

            if (
                args.passes >= 2
                and 1 in experiment.pass_step_errors
                and 2 in experiment.pass_step_errors
            ):

                correlation = (
                    pearson_correlation(
                        experiment.pass_step_errors[1],
                        experiment.pass_step_errors[2],
                    )
                )

                summary_rows.append({
                    "metric":
                        "pass_1_vs_2_step_error_correlation",

                    "value":
                        correlation,

                    "unit":
                        "Pearson r",
                })

                print()
                print(
                    "PASS 1 vs PASS 2"
                )

                print(
                    "  layer-spacing error "
                    "correlation: "
                    f"r = {correlation:.4f}"
                )

            logger.write_summary(
                summary_rows
            )

            status = "completed"

            print()
            print(
                "Experiment completed."
            )

            print()
            print(
                "NOTE: machine remains at "
                "the final measurement position."
            )

    except KeyboardInterrupt:

        status = "interrupted"

        print()
        print()
        print(
            "INTERRUPTED."
        )

        print(
            "No further movement commands "
            "will be sent."
        )

    except Exception as exc:

        status = "error"
        error_text = repr(exc)

        print()
        print(
            "EXPERIMENT ABORTED:"
        )

        print(
            repr(exc)
        )

        raise

    finally:

        logger.metadata(
            "run_status",
            status,
        )

        logger.metadata(
            "run_end_timestamp",
            now_iso(),
        )

        if error_text:

            logger.metadata(
                "run_error",
                error_text,
            )

        if (
            experiment is not None
            and experiment.encoder_sign
            is not None
        ):

            logger.metadata(
                "detected_encoder_sign",
                experiment.encoder_sign,
            )

        logger.close()

        print()
        print(
            "Run directory:"
        )

        print(
            f"  {run_dir}"
        )

        print()
        print(
            "Files:"
        )

        print(
            "  metadata.csv"
        )

        print(
            "  moves.csv"
        )

        print(
            "  layers.csv"
        )

        print(
            "  encoder_samples.csv"
        )

        print(
            "  summary.csv"
        )

    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )