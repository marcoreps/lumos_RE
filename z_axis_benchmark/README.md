# Z-axis benchmarking before and after modifications

I began looking into the Z axis after seeing some kind of periodic banding problem in 3D glass engraving (see [close up](../images/3d_glass_fine_tuned_side_banding_Z_axis_problem.jpg)). An external Parker MX80L linear actuator with sub-nm-resolution encoder was used to measure actual Z motion independently of the engraver's own open-loop motion controller. In the original factory config, a commanded 20 µm layer sometimes resulted in 7 µm or as much as 33 µm of actual movement. The error pattern was nearly identical on multiple passes.

I found and fixed a firmware bug, replaced the linear rail carriages, and replaced the factory trapezoidal leadscrews with cheapo rolled ball screws. Then I repeated the original layer-spacing test with the same parameters and got sufficiently good results.

## The before/after

| Layer-spacing metric | Factory pass 1 | Factory pass 2 | Modified pass 1 | Modified pass 2 |
|:--|--:|--:|--:|--:|
| Mean physical increment | 19.931 µm | 19.939 µm | 19.898 µm | 19.952 µm |
| Standard deviation | **5.082 µm** | **5.236 µm** | **0.622 µm** | **0.626 µm** |
| Minimum physical increment | 7.126 µm | 7.293 µm | 17.356 µm | 18.107 µm |
| Maximum physical increment | 32.385 µm | 32.686 µm | 21.801 µm | 22.321 µm |
| RMS error relative to 20 µm | **5.072 µm** | **5.226 µm** | **0.630 µm** | **0.628 µm** |
| Final cumulative position error | −17.19 µm | −15.29 µm | −25.60 µm | −11.98 µm |

Huge layer-to-layer jumps are solved, some absolute accumulating gain error remains but that is not a visible problem in 3D glass engraving.

## Method

The machine's Z motion was measured with the Renishaw encoder in a Parker MX80L linear stage read through a Trinamic TMC4671 devboard. The encoder interpolation is `20 µm / 65,536 ≈ 0.305 nm/count`, which is not measurement accuracy of course.

Both experiments used the normal G-code command path, not direct RS485 injection. With these params:

| Setting | Value |
|:--|:--|
| Pitch / interval count | 20 µm × 250 |
| Span / passes | 5.0 mm, two passes |
| Measurement direction | Positive Z |
| Same-direction preload | 0.3 mm |
| Measurement feed / reposition feed | 60 / 600 mm/min |
| Encoder burst per position | 0.1 s |
| Settling guard / stable window | 0.1 / 0.2 s |
| Stability acceptance | ≤ 0.1 µm peak-to-peak |

The "before" run was `logs/layer_spacing_20260925_190700` (initial reported Lumos Z: `90.290 mm`). The "after" run with all optimizations is `logs/layer_spacing_20261031_130351` (first commanded layer position: `60.390 mm`).

## Hardware upgrades

The Z-Lift mechanism originally used non-Hiwin MGN15H-shaped Linear rails and two 3D printer grade trapezoidal-lead-screw-integral-stepper-motors with plastic nuts. The steppers also act as the fixed axial bearings. Reasonable in my opinion because this system is permanently preloaded by gravity. Both stepper drivers for the z-axis receive the same step- & direction signal on the PCB, there is no independent driving for tilt correction. In my early prototype unit tilting happened often and the head would get stuck somewhere until forcefully corrected. It would have been better to drive both lead screws with one motor and to synchronize them with a belt but there is no room for that. One of the linear rail carriages was bone dry and hard to move by hand. Lubrication and massaging helped a bit but it seemed damaged or of poor quality so I replaced both carriages with original Hiwin parts. One of the lead screws was severely bent. I tried replacing both with igus dryspin DST-LS-8X2-R stainless steel lead screws with igus DST-JFRM-PL-0001-DS8X2 preload nuts but these had very high radial runout around the nut perimeter and very high friction under the heavy load of the laser head. In the end I replaced the igus parts with BPGF-C7-12-2-L300 low cost rolled ball screws and CXJV-A-D20-d5-e10 shaft couplings, both having unproblematic radial runout. This needed CNC modification of the Z-lift-plate to account for the 20mm diameter nut bodies. To eliminate cogging errors I upgraded the stepper motors to closed loop ESS17-04 motors. There is plenty of room for such longer motors in the machine, it just needs to be NEMA17. The closed loop steppers needed elecontric modifications on the aux PCB as well, not sure if I would generally recommend this. Ball screws and lubrication of the linear rails were probably the only things I would consider mandatory.


## Firmware bug

The Z chain of command in the machine is roughly:

```text
G-code -> file system on single board computer -> MCU1 -> RS485 -> MCU2 -> pulses to stepper drivers
```

The lift MCU2 accepts absolute positions on a 5 µm grid, but the original normal MCU1 G-code processor sends values truncated to a 10 µm grid. Direct RS485 command `0x0019` could bypass that upstream conversion.


After LLM-assisted firmware patch, a normal-G-code **17 µm** sweep on October 31 reported **15/20 µm increments**, consistent with the expected 5 µm position lattice, and the external encoder followed those commands. That is strong behavioral evidence that the old upstream 10 µm quantization was corrected, although it is not a fresh RS485 packet capture.

The **matched 20 µm sweep alone cannot test that quantization bug**, because 20 µm is divisible by both the 5 and 10 µm grids. Likewise, these results do not separate the effect of changing the screw lead, rails, firmware, mounting geometry, or the Z measurement region.


