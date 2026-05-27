#!/usr/bin/env python
"""Generate ParaView .pvd file to animate the rotating-magnet snapshots."""
from pathlib import Path

FREQ = 5.0
PERIOD = 1.0 / FREQ  # 0.2 s
N_ANGLES = 36
DT = PERIOD / N_ANGLES

pvd_path = Path("rotate_animation.pvd")

lines = [
    '<?xml version="1.0"?>',
    '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
    '  <Collection>',
]

for i in range(N_ANGLES):
    angle_deg = i * 10.0
    timestep = i * DT
    vtu_rel = f"mesh/results_angle_{angle_deg:03.0f}/case_angle_{angle_deg:03.0f}_t0001.vtu"
    lines.append(f'    <DataSet timestep="{timestep:.6f}" group="" part="0" file="{vtu_rel}"/>')

lines.append('  </Collection>')
lines.append('</VTKFile>')

pvd_path.write_text('\n'.join(lines) + '\n')
print(f"Wrote {pvd_path}")
print(f"  {N_ANGLES} datasets, dt = {DT:.6f} s, period = {PERIOD:.3f} s")
print(f"  Open this .pvd file in ParaView for time-series animation.")
