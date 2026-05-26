# gmsh-elmer — Claude Code Skill

End-to-end **Gmsh → Elmer FEM** workflow skill for Claude Code. Covers electromagnetic and rotating-machinery simulations: geometry, meshing, ElmerGrid conversion, solver input (WhitneyAV, magnetostatics, transient rotation), and debugging common failure modes.

## Installation

```bash
# Clone the repository
git clone <repo-url> gmsh-elmer-skill

# Install the skill into Claude Code
# Option A: register as a user skill
mkdir -p ~/.claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md ~/.claude/skills/gmsh-elmer/

# Option B: register as a project skill (in your project root)
mkdir -p .claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md .claude/skills/gmsh-elmer/
```

Restart Claude Code (or open a new session) — the skill auto-loads when you mention Gmsh, Elmer, WhitneyAV, magnetostatics mesh, or rotating machinery.

## What this skill covers

| Stage | Tool | Content |
|-------|------|---------|
| Geometry | Gmsh (OpenCASCADE) | Boolean ops, surface classification, conformal/non-conformal interfaces |
| Meshing | Gmsh | Distance-based size fields, physical groups, Elmer v2.2 export |
| Conversion | ElmerGrid | Renumbering rules, `-autoclean` flag |
| Solver | ElmerSolver | WhitneyAV, CalcFields, RigidMeshMapper, Mortar BCs |
| Debugging | — | Tree gauge crash on Windows, BiCGStabl vs BiCGStabL, `Real` keyword trap |

## Quick test

The `TEST/` directory contains a complete worked example — a diametrical NdFeB permanent magnet simulation. After installing the skill, copy the prompt from `prompt.md` into Claude Code to run the full pipeline.

```
TEST/
├── magnet_mesh.py       ← Gmsh mesh generator
├── case_steady.sif      ← Elmer solver input
├── run_steady.bat        ← Windows one-click runner
├── mesh.msh              ← Pre-generated mesh (~3 MB)
└── results/
    └── case_t0001.vtu    ← Sample VTU output (~4 MB)
```

## Dependencies

- [Gmsh](https://gmsh.info/) ≥ 4.13 (Python API: `pip install gmsh`)
- [Elmer FEM](https://www.csc.fi/web/elmer) 9.0
- [ParaView](https://www.paraview.org/) ≥ 5.10 (for visualization)

## ParaView Quick Check

After running the simulation, open `TEST/results/case_t0001.vtu` in ParaView. To see the dipole pattern (instead of parallel arrows):

1. **File → Open** `case_t0001.vtu` → click **Apply**
2. Add **Clip** filter: Box, `[-0.04, -0.04, -0.04]` to `[0.08, 0.08, 0.08]`, check **Invert**
3. Add **Glyph** filter: Orientation = `magnetic flux density`, Scale Factor = `0.015`

This clips to the magnet region (±4 cm), revealing the dipole field that is otherwise hidden by far-field arrows.

## Key fixes documented in this skill

- **`Real` keyword trap** — `Magnetization 1 = Real 955000.0` silently sets M=0
- **Tree gauge crash** — Elmer 9.0 Windows crashes during gauge tree construction
- **BiCGStabl vs BiCGStabL** — BiCGStabL + ILU0 diverges on Windows; BiCGStabl works
- **GMRES false convergence** — Converges to trivial A=0 solution when RHS non-zero
- **Surface classification** — Use bounding-box Z-extent, not centroid
- **ElmerGrid renumbering** — Tags are renumbered sequentially from 1

## License

MIT
