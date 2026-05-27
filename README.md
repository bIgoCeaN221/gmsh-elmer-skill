# gmsh-elmer — Claude Code Skill

End-to-end **Gmsh → Elmer FEM** workflow skill for Claude Code. Covers electromagnetic and rotating-machinery simulations: geometry, meshing, ElmerGrid conversion, solver input (WhitneyAV, magnetostatics, transient rotation, force/torque), ParaView visualization (PVD time-series, force glyphs), and debugging common failure modes.

## Installation

```bash
# Clone the repository
git clone git@github.com:bIgoCeaN221/gmsh-elmer-skill.git

# Install the skill into Claude Code
# Option A: register as a user skill
mkdir -p ~/.claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md ~/.claude/skills/gmsh-elmer/

# Option B: register as a project skill (in your project root)
mkdir -p .claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md .claude/skills/gmsh-elmer/
```

Restart Claude Code (or open a new session) — the skill auto-loads when you mention Gmsh, Elmer, WhitneyAV, magnetostatics mesh, rotating machinery, force/torque computation, or PVD animation.

## What this skill covers

| Stage | Tool | Content |
|-------|------|---------|
| Geometry | Gmsh (OpenCASCADE) | Boolean ops, surface classification, conformal/non-conformal interfaces |
| Meshing | Gmsh | Distance-based size fields, physical groups, Elmer v2.2 export |
| Conversion | ElmerGrid | Renumbering rules, `-autoclean` flag |
| Solver | ElmerSolver | WhitneyAV, CalcFields, RigidMeshMapper, Mortar BCs |
| Transient rotation | ElmerSolver | Time-varying magnetization via MATC, static-mesh approach (Windows-safe) |
| Force & torque | ElmerSolver + meshio | `Calculate Nodal Forces`, GeometryIds filtering, cross-product torque |
| Multi-file animation | ParaView | PVD XML aggregation for scattered VTU directories |
| Force visualization | ParaView | Glyph scaling for nano-Newton fields, Calculator quoting, torque density |
| Debugging | — | Tree gauge crash on Windows, BiCGStabl vs BiCGStabL, `Real` keyword trap |

## Repository examples

This repository includes two complete, runnable examples:

### `static_magnet/` — Static NdFeB permanent magnet

A diametrically-magnetised NdFeB cylinder (D=30 mm, H=80 mm) in a 0.5 m air box. Steady-state WhitneyAV solve. The simplest starting point.

```
static_magnet/
├── magnet_mesh.py       ← Gmsh mesh generator
├── case_steady.sif      ← Elmer solver input
├── run_steady.bat        ← Windows one-click runner
├── mesh.msh              ← Pre-generated mesh (~3 MB)
└── results/
    └── case_t0001.vtu    ← Sample VTU output
```

### `rotating_magnet/` — Rotating PM (multi-angle quasi-static scan)

Same geometry as the static case, but magnetisation rotates. Generates 36 steady-state SIF files (0°–350°), solves each, then aggregates into a ParaView PVD animation. Demonstrates the Windows-compatible approach to rotation without RigidMeshMapper.

```
rotating_magnet/
├── magnet_mesh.py       ← Same mesh generator as static
├── case_rotate.sif      ← Example SIF (angle 0°)
├── rotate_scan.py       ← Generates 36 SIF files + batch runner
├── create_pvd.py        ← PVD animation file generator
├── run_rotate.bat        ← Windows one-click pipeline
├── mesh.msh              ← Pre-generated mesh (~3 MB)
└── results/
    └── case_angle_000_t0001.vtu  ← Sample VTU (angle 0°)
```

Both examples work with the same mesh; after installing the skill, copy a prompt from `prompt.md` into Claude Code to run either pipeline.

## Related projects

- **`SingleRotateMagnetFEA/`** — Larger-scale rotating magnet (5 m box, 300 RPM, 36 angles). Same technique as `rotating_magnet/` but at production scale.
- **`SingleRotateMagnetTinyTargetFEA/`** — Transient WhitneyAV with a copper sphere (D=5 cm) at (0.5, 0, 0). Time-varying magnetization generates eddy currents in the sphere; CalcFields computes nodal forces; meshio post-processing extracts force and torque vs time.

## Dependencies

- [Gmsh](https://gmsh.info/) ≥ 4.13 (Python API: `pip install gmsh`)
- [Elmer FEM](https://www.csc.fi/web/elmer) 9.0
- [ParaView](https://www.paraview.org/) ≥ 5.10 (for visualization)
- [meshio](https://github.com/nschloe/meshio) ≥ 5.0 (Python: `pip install meshio` — for VTU force/torque post-processing)

## ParaView Quick Check

After running the simulation, open `static_magnet/results/case_t0001.vtu` in ParaView. To see the dipole pattern (instead of parallel arrows):

1. **File → Open** `case_t0001.vtu` → click **Apply**
2. Add **Clip** filter: Box, `[-0.04, -0.04, -0.04]` to `[0.08, 0.08, 0.08]`, check **Invert**
3. Add **Glyph** filter: Orientation = `magnetic flux density`, Scale Factor = `0.015`

This clips to the magnet region (±4 cm), revealing the dipole field that is otherwise hidden by far-field arrows.

To see a **wider field of view**, increase the Clip box size (e.g., `[-0.15, -0.15, -0.15]` to `[0.20, 0.20, 0.20]`). The Clip + Glyph approach works at any range — adjust the box to your region of interest.

## ParaView: multi-file animation (PVD)

When VTU files are scattered across separate subdirectories (e.g., one per rotation angle or timestep), ParaView cannot auto-play them as a time series. Generate a `.pvd` XML collection:

```python
# create_pvd.py
from pathlib import Path

N_STEPS = 36
DT = 1.0 / 180.0  # example

lines = [
    '<?xml version="1.0"?>',
    '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
    '  <Collection>',
]
for i in range(N_STEPS):
    timestep = i * DT
    vtu_rel = f"results_angle_{i*10:03d}/case_angle_{i*10:03d}_t0001.vtu"
    lines.append(f'    <DataSet timestep="{timestep:.6f}" group="" part="0" file="{vtu_rel}"/>')
lines.append('  </Collection>')
lines.append('</VTKFile>')

Path("animation.pvd").write_text('\n'.join(lines) + '\n')
```

Open the `.pvd` file in ParaView — all VTU files appear as a single time series with playback controls.

## ParaView: force & torque visualization

For simulations with `Calculate Nodal Forces = True`, the VTU output contains a `nodal force` point-data field. Visualizing it requires special handling because the values are very small (~10⁻⁷ N).

**Glyph arrows for force:**
1. Open VTU → **Apply**
2. Add **Glyph** filter
3. Set **Orientation Array** = `nodal force`, **Scale Array** = `nodal force`
4. Set **Scale Factor** = `1000000` (the field is ~10⁻⁷ N; default scale produces invisible arrows)
5. Adjust **Glyph Type** to Arrow or 3D Glyph as needed

**Torque computation in ParaView Calculator:**
1. Apply **Calculator** filter
2. Compute position relative to rotation center, e.g.: `coords - (0.5, 0.0, 0.0)`
3. Apply another **Calculator** for torque density: `cross(r_vec, 'nodal force')`
   - Field names with spaces (like `nodal force`) must be **single-quoted** in expressions
4. The result is torque density per node (N·m)

**Force on a specific body:** Use **Threshold** filter on `GeometryIds` to isolate a body, then inspect `nodal force` on only its nodes.

## Key fixes documented in this skill

- **`Real` keyword trap** — `Magnetization 1 = Real 955000.0` silently sets M=0
- **Tree gauge crash** — Elmer 9.0 Windows crashes during gauge tree construction
- **BiCGStabl vs BiCGStabL** — BiCGStabL + ILU0 diverges on Windows; BiCGStabl works
- **GMRES false convergence** — Converges to trivial A=0 solution when RHS non-zero
- **Surface classification** — Use bounding-box Z-extent, not centroid
- **ElmerGrid renumbering** — Tags are renumbered sequentially from 1
- **RigidMeshMapper unavailable on Windows** — Elmer 9.0 Windows build lacks the module; use transient WhitneyAV with time-varying magnetization and static mesh instead
- **`nodal force` quoting in ParaView Calculator** — Field names with spaces must be single-quoted: `'nodal force'`
- **Glyph arrows invisible for nano-scale fields** — Set Scale Factor manually (e.g., 1,000,000 for ~10⁻⁷ N fields)

## License

MIT
