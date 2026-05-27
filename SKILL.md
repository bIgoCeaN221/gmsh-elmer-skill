---
name: gmsh-elmer
description: >
  End-to-end Gmsh → Elmer FEM workflow for electromagnetic and rotating-machinery problems.
  Use this skill whenever the user needs to: generate a 3D mesh with Gmsh for Elmer,
  create Elmer SIF solver-input files, set up WhitneyAV / magnetostatic / rotating
  simulations, or debug Gmsh-to-Elmer pipeline issues.  Triggers on mentions of "Gmsh
  + Elmer", "mesh for Elmer", "ElmerGrid", "case.sif", "RigidMeshMapper", "WhitneyAV",
  "magnetostatics mesh", "rotating machinery FEM", "electromagnetic simulation mesh",
  "force on target", "torque computation", or any request to go from CAD/geometry to
  Elmer solver.
---

# Gmsh → Elmer  electromagnetic / rotating-machinery workflow

## Overview

The pipeline has four stages:

```
Geometry ──▶ Mesh ──▶ Elmer conversion ──▶ Solver
  (Gmsh)     (Gmsh)    (ElmerGrid)       (ElmerSolver + case.sif)
```

This skill covers the **patterns** that work across geometry types (cylinders, boxes,
arbitrary CAD), not templates tied to one specific shape.  Each section below documents
both the "happy path" and the failure modes we hit and fixed.

---

## Stage 1 — Gmsh geometry (OpenCASCADE kernel)

### 1.1 API version detection

Gmsh ≥ 4.13 changed OCC API return types from `[(dim, tag)]` to bare `int`.  Always
guard every `addCylinder` / `addBox` / `cut` / `fuse` call:

```python
def _vol_tag(result):
    if isinstance(result, int):
        return result
    return result[0][1] if isinstance(result[0], tuple) else result[0]

mag = gmsh.model.occ.addCylinder(0, 0, -h/2, 0, 0, h, r)
mag_tag = mag if isinstance(mag, int) else mag[1]
```

The same pattern applies to `cut`, `fuse`, `fragment` — their first return value may be
a list of ints or a list of tuples.

### 1.2 Boolean operation order (conformal interfaces)

When domain A is split into "inner" (rotating) and "outer" (stationary) by interface
surface S at radius R, the order matters for getting conformal (shared-node) interfaces:

```
Correct (conformal):
  1. stationary = box - rotor     # remove box, KEEP rotor
  2. rotating   = rotor - inner   # remove rotor, KEEP inner

Wrong (overlapping / broken):
  1. rotating   = rotor - inner   # remove rotor (lost!)
  2. stationary = box - ???       # can't reference deleted rotor
```

The pattern: **cut the outer part first (keep the tool), then cut the tool (keep the
innermost)**.  This ensures every interface surface is shared by exactly two volumes.

For non-conformal interfaces (needed for RigidMeshMapper rotation), introduce a tiny
radial offset between the two sides so Gmsh meshes them independently.  See §4.2.

### 1.3 Surface classification (robust method)

After Boolean operations, surfaces are renumbered unpredictably.  Don't rely on tag
numbers.  Classify by **geometric properties** instead.

**Mistake we made**: using centroid (bounding-box centre) to distinguish cylindrical
side-walls from flat caps.  A cylinder side-wall at r=R has bounding-box centre at
(0, 0, z_mid) → r_xy ≈ 0, same as the caps.  The side-wall gets misclassified.

**Correct method**: use **Z-extent** of the bounding box:

```python
def classify_cyl_surfaces(vol_tag):
    surfs = gmsh.model.getBoundary([(3, vol_tag)], combined=False)
    result = {"top": [], "bot": [], "side": [], "other": []}
    for s in surfs:
        bbox = gmsh.model.getBoundingBox(2, s[1])
        z_ext = bbox[5] - bbox[2]   # Zmax - Zmin
        cz    = (bbox[2] + bbox[5]) / 2
        if z_ext < 1e-4:            # flat face → cap
            if cz > 0.01:   result["top"].append(s[1])
            elif cz < -0.01: result["bot"].append(s[1])
            else:            result["other"].append(s[1])
        else:                        # tall face → side wall
            result["side"].append(s[1])
    return result
```

For identifying which side-wall is which (e.g., inner vs outer of a gap volume at
different radii), use the XY bounding-box half-extent, NOT the centroid:

```python
def surf_radius(surf_tag):
    bbox = gmsh.model.getBoundingBox(2, surf_tag)
    rx = (bbox[3] - bbox[0]) / 2
    ry = (bbox[4] - bbox[1]) / 2
    return max(rx, ry)
```

This works because the bounding box of a cylindrical face at radius R spans [-R, +R]
in X and Y, so the half-extent IS the radius.

### 1.4 Mesh size fields (multi-scale domains)

For geometries with mm-scale features in m-scale domains (ratio > 100:1), use a
**distance-based mesh size field** rather than per-entity characteristic lengths:

```python
# Collect source faces (the smallest features)
src_faces = magnet_side + magnet_top + magnet_bot

dist_f = gmsh.model.mesh.field.add("Distance")
gmsh.model.mesh.field.setNumbers(dist_f, "FacesList", src_faces)

thresh_f = gmsh.model.mesh.field.add("Threshold")
gmsh.model.mesh.field.setNumber(thresh_f, "InField", dist_f)
gmsh.model.mesh.field.setNumber(thresh_f, "SizeMin", lc_fine)    # at source
gmsh.model.mesh.field.setNumber(thresh_f, "SizeMax", lc_coarse) # at far field
gmsh.model.mesh.field.setNumber(thresh_f, "DistMin", 0.005)
gmsh.model.mesh.field.setNumber(thresh_f, "DistMax", 2.5)

bg = gmsh.model.mesh.field.add("Min")
gmsh.model.mesh.field.setNumbers(bg, "FieldsList", [thresh_f])
gmsh.model.mesh.field.setAsBackgroundMesh(bg)
```

**Multiple refinement sources**: when the geometry has several small features at
different locations (e.g., a magnet at the origin AND a copper sphere at (0.5,0,0)),
include faces from ALL small features in the `src_faces` list.  The Distance field
will automatically refine each region:

```python
src_faces = magnet_side + magnet_top + magnet_bot  # magnet region
src_faces.append(sphere_surface)                     # copper sphere region

# Use the SMALLEST lc among all refinement targets as SizeMin
LC_MIN = min(lc_magnet, lc_sphere)  # e.g., 0.002 m for a 5cm sphere
```

**Key settings** (set BEFORE `generate(3)`):
- `Mesh.MshFileVersion = 2.2` (Elmer compatibility; a NUMBER option, not string)
- `Mesh.Algorithm3D = 1` (Delaunay)
- `Mesh.Optimize = 1` + `Mesh.OptimizeNetgen = 1`
- `Mesh.ElementOrder = 1` (linear; Elmer can elevate if needed)

### 1.5 Physical groups

Use semantic tag ranges so the mapping to Elmer is clear:
- Volumes: 100, 200, 300, ... (one per material region)
- Boundaries: 10, 11, 12, ... for external BCs; 20, 21, ... for interfaces

ElmerGrid **renumbers** them (see §3.1), so the tags are just for human readability in
Gmsh.  Use `gmsh.model.addPhysicalGroup(dim, [tags], tag=N, name="...")` for each.

**Multi-body geometry example** (magnet + copper target + air):
| Tag | Name | Purpose |
|-----|------|---------|
| 100 | magnet | NdFeB magnet body |
| 200 | copper_sphere | Conductive target body |
| 300 | air | Surrounding air |
| 10 | far_field | BC: A = 0 at infinity |
| 11–13 | mag_top/bot/side | Magnet surface faces |
| 14 | sphere_surface | Target surface (internal, natural BC) |

---

## Stage 2 — Mesh export & quality check

### 2.1 Export formats

```python
gmsh.write("mesh.msh")   # MSH 2.2 (set Mesh.MshFileVersion=2.2 before generate)
gmsh.write("mesh.mesh")  # Elmer native (may not be available in all builds)
```

Always save a v4 `.msh` copy too (`magnet.msh`) for re-opening in Gmsh GUI to inspect.

### 2.2 Quick quality check

After meshing, verify no physical group came out empty (silent failure mode):

```python
for dim, tag in gmsh.model.getPhysicalGroups():
    ents = gmsh.model.getEntitiesForPhysicalGroup(dim, tag)
    name = gmsh.model.getPhysicalName(dim, tag)
    assert len(ents) > 0, f"Physical group '{name}' (tag={tag}) is EMPTY!"
```

An empty physical group means surface classification failed — revisit §1.3.

---

## Stage 3 — ElmerGrid conversion

### 3.1 Renumbering (critical)

**ElmerGrid renumbers everything sequentially from 1, ordered by the original tag value.**
Physical group tags are NOT preserved in Elmer.

The mapping for tags [10, 11, 12, 13, 20] and [100, 200, 300]:
```
Boundaries:  10→1, 11→2, 12→3, 13→4, 20→5
Bodies:     100→1, 200→2, 300→3
```

The `mesh.names` file (generated by ElmerGrid) records the mapping:

```
$ magnet = 1
$ air_rotating = 2
$ far_field = 1
$ sliding_rotor = 5
```

**Always read `mesh.names`** before writing the SIF.  All `Target Bodies` and
`Target Boundaries` in the SIF must use the **renumbered** indices.

Command:
```bash
ElmerGrid 14 2 mesh.msh -autoclean
```
This creates a `mesh/` subdirectory with `mesh.nodes`, `mesh.elements`, `mesh.boundary`,
`mesh.header`, `mesh.names`.

### 3.2 The `-autoclean` flag

Removes lower-dimensional elements (edges, points) that Gmsh sometimes includes.
Without it, Elmer may see "mixed dimension" elements and error out during assembly.

---

## Stage 4 — Elmer SIF file

### 4.1 Required structure

Every SIF needs these blocks, in this order:

```
Header          — Mesh DB path, Results Directory
Simulation      — Type (Steady/Transient), timestepping
Constants       — Permeability/Permittivity of Vacuum
Solver 1..N     — Procedure, linear system, element type
Equation 1..M   — Active Solvers list
Material 1..K   — Properties per material
Body 1..K       — Target Bodies, Equation, Material, [Body Force], [Mesh Rotate]
Body Force 1..P — Source terms (magnetization, current, etc.)
Boundary Condition 1..B — Dirichlet / Neumann / Mortar BCs
```

**Common mistake**: having `Equation = 1` in Body blocks without an `Equation 1` block.
Elmer warns "There are no Equations in the system!" and may crash.  Always include:

```
Equation 1
  Name = "Model"
  Active Solvers(3) = 1 2 3
End
```

### 4.2 WhitneyAV solver (magnetostatics)

The go-to solver for 3D magnetic problems.  **Working setup for Elmer 9.0 Windows**
(tree gauge crashes on Windows — see §4.2.1):

```
Solver 1
  Equation = "WhitneyAV"
  Procedure = "MagnetoDynamics" "WhitneyAVSolver"
  Stabilize = True              ! critical for convergence
  Optimize Bandwidth = True
  
  Linear System Solver = "Iterative"
  Linear System Iterative Method = "BiCGStabl"   ! not BiCGStabL
  Linear System Preconditioning = "ILU0"
  Linear System Max Iterations = 2000
  Linear System Convergence Tolerance = 1.0e-08
  
  Steady State Convergence Tolerance = 1.0e-06
End
```

**CRITICAL:** Magnetization values in the Material section must NOT use
the `Real` keyword prefix (see §4.4).  `Real` is a MATC variable name,
not a type specifier — using it silently zeros out the magnetization.

On **Linux** where tree gauge works, BiCGStabL + ILU1 is fine:

```
Solver 1
  Equation = "WhitneyAV"
  Procedure = "MagnetoDynamics" "WhitneyAVSolver"

  Linear System Solver = "Iterative"
  Linear System Iterative Method = "BiCGStabL"
  Linear System Preconditioning = "ILU1"
  Linear System Max Iterations = 3000
  Linear System Convergence Tolerance = 1.0e-08

  Use Tree Gauge = True        ! regularization for A
  Average Within Materials = True
  Element = "n:0 e:1"
End
```

Direct solver on Windows: `Use Tree Gauge = True` is enabled by default when
using the direct solver → guaranteed crash.  Explicitly setting
`Use Tree Gauge = False` with the direct solver leads to a singular matrix.
**Avoid direct solvers on Windows for WhitneyAV**.

#### 4.2.1 Tree gauge on Windows

Elmer 9.0 on Windows crashes **silently** during gauge tree construction
(after `MGDynAssembly`, before `DefaultSolve`).  Without tree gauge:

| Method | ILU0 | ILU1 | ILU2 |
|--------|------|------|------|
| **BiCGStabl + Stabilize** | Converges reliably | Mixed | Untested |
| **GMRES** | Converges to trivial (A=0) | Untested | Untested |
| **BiCGStabL** | Diverges | Diverges | NaN/breakdown |

**Recommendation:** BiCGStabl + ILU0 + `Stabilize = True` is the working
combination on Windows.  GMRES also converges (fast) but to the trivial
zero solution when the RHS is non-zero — misleadingly fast convergence.

**CRITICAL SIF syntax:**
```
Magnetization 1 = 955000.0    ! correct: plain number
Magnetization 1 = Real 955000.0  ! WRONG: "Real" = MATC variable → ignored!
```
The `Real` keyword before a numeric value triggers MATC/Lua evaluation;
the parser treats `Real` as a variable name, silently ignoring the value.
This causes the magnetization source term to be zero → trivial solution.

### 4.3 CalcFields (post-processing)

Always add a separate solver to compute B and H from A:

```
Solver 2
  Exec Solver = After All         ! or After Timestep for transient
  Equation = "CalcFields"
  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"
  Potential Variable = "AV"
  Calculate Magnetic Flux Density = True
  Calculate Magnetic Field Strength = True
  Calculate Nodal Fields = True
  Linear System Solver = "Iterative"
  Linear System Iterative Method = "CG"
  Linear System Preconditioning = "ILU0"
End
```

For force/torque computation, add these to CalcFields (see §5.5):

```
  Calculate Nodal Forces = True
  Calculate Current Density = True
```

The nodal force field is named `"nodal force"` (note the space!) in the VTU output.
See §8.2 for ParaView handling of space-containing field names.

### 4.4 Permanent magnets (magnetization)

Magnetization goes in the **Material** section, in A/m (M = Br/μ₀):

```
Material 1
  Name = "NdFeB"
  Relative Permeability = 1.05
  Magnetization 1 = 955000.0   ! Mx [A/m] — plain number, NO "Real" prefix!
  Magnetization 2 = 0.0
  Magnetization 3 = 0.0
End
```

For **time-varying or coordinate-dependent** magnetization, use MATC:

```
  ! Rotating magnetization (ω = 2π·RPM/60):
  Magnetization 1 = Variable Time
    Real MATC "M0 * cos(omega * tx)"
  Magnetization 2 = Variable Time
    Real MATC "M0 * sin(omega * tx)"

  ! Radial magnetization (outward from Z axis):
  Magnetization 1 = Variable Coordinate
    Real MATC "M0 * tx[0] / sqrt(tx[0]^2 + tx[1]^2 + 1e-12)"
```

**Important**: `Real MATC "..."` is correct syntax — the `Real` keyword here
is part of the MATC expression structure (unlike `Real 955000.0` which is wrong
for plain numbers).  The MATC `Real` tells Elmer the expression returns a
real-valued result.

### 4.5 Far-field boundary (A = 0)

For the Whitney AV formulation, the Dirichlet condition sets edge components of A:

```
Boundary Condition 1
  Target Boundaries(1) = 1   ! far_field (after ElmerGrid renumber)
  Name = "FarField"
  AV {e} 1 = Real 0.0
  AV {e} 2 = Real 0.0
  AV {e} 3 = Real 0.0
End
```

Internal boundaries (material interfaces) need NO explicit BC — flux continuity is
the natural boundary condition.

### 4.6 Conductive materials (for eddy currents)

For bodies with non-zero conductivity (copper, aluminum, etc.):

```
Material 2
  Name = "Copper"
  Relative Permeability = 1.0
  Electric Conductivity = 5.96e7   ! [S/m] for copper at room temperature
End
```

The WhitneyAV solver's transient formulation includes the σ·∂A/∂t term, which
automatically captures eddy currents.  No extra solver configuration is needed
beyond setting `Simulation Type = Transient` and the conductivity value.

Common conductivity values [S/m]:
- Copper: 5.96×10⁷
- Aluminum: 3.5×10⁷
- Stainless steel: 1.4×10⁶

---

## Stage 5 — Rotation / rotating machinery

### 5.1 Three approaches (ranked by complexity)

| Approach | Mesh | Solver | Windows? | Use case |
|----------|------|--------|----------|----------|
| Multi-angle steady-state | Conformal (no rotor) | WhitneyAV only | Yes | Pure magnetostatics, no eddy currents |
| Transient static-mesh | Conformal (no rotor) | Transient WhitneyAV | Yes | Eddy currents, force/torque on targets |
| Transient RigidMeshMapper | Non-conformal | RigidMeshMapper + WhitneyAV | No (Windows Elmer 9.0 lacks the module) | Full transient with mesh rotation |

**Decision tree:**
- Only need B-field animation? → Multi-angle scan (§5.2)
- Need eddy currents / forces / torque on targets? → Transient static-mesh (§5.4)
- Need physical mesh rotation + Mortar BCs? → RigidMeshMapper (§5.3, Linux only)

### 5.2 Multi-angle scan (simplest, always works)

Run steady-state at N discrete angles.  Magnetization direction at angle θ:
```
Mx(θ) = M₀·cos(θ),   My(θ) = M₀·sin(θ)
```

Generate one SIF per angle, changing only the `Magnetization 1/2` values.
A Python script can batch-generate these (the `rotate_scan.py` pattern):

```python
# Pseudocode for rotate_scan.py
for i in range(N_ANGLES):
    theta = 2 * pi * i / N_ANGLES
    mx = M0 * cos(theta)
    my = M0 * sin(theta)
    write_sif(angle=i*360/N_ANGLES, mx=mx, my=my)
```

**Workflow:**
1. Generate conformal mesh (no rotor domain, no sliding interfaces): `magnet + air`
2. Run `python rotate_scan.py` → N SIF files in `magnet_mesh/mesh/`
3. Run each SIF with ElmerSolver (batch loop)
4. Aggregate VTU files into a PVD time series for ParaView animation (see §7.1)

**Mesh note**: No rotor cylinder, no sliding interfaces.  The multi-angle scan
only needs magnet + air bodies.  The "rotation" is purely in the magnetization
direction, not the geometry.

### 5.3 Transient RigidMeshMapper (full physics, Linux only)

**⚠ Elmer 9.0 on Windows does NOT include the RigidMeshMapper solver module.**
The SIF parser will reject `Rotor Number` and related keywords.  If you need
this approach, use Elmer on Linux or a custom-compiled Windows build with the
RigidMeshMapper module enabled.

**Prerequisite**: non-conformal mesh (separate nodes at the sliding interface).

To get a non-conformal mesh in Gmsh, offset the rotor/stator cut radius by ~0.1 mm:
```
rotor_r = 0.025             # rotating side
rotor_r_stator = 0.0251     # stationary side (0.1 mm larger)
```
Gmsh meshes the two cylindrical surfaces independently → separate node sets.

**SIF additions**:

RigidMeshMapper solver (executes BEFORE each timestep):
```
Solver 1
  Exec Solver = Before Timestep
  Equation = "Mesh"
  Procedure = "RigidMeshMapper" "RigidMeshMapper"
  Rotor Number = 1
  Rotation Origin 1(3) = Real 0.0 0.0 0.0
  Rotation Axis 1(3)   = Real 0.0 0.0 1.0
  Rotation Angular Velocity 1 = Real $ omega
  Mesh Update = True
End
```

Bodies that rotate get `Mesh Rotate = 1`:
```
Body 1
  Target Bodies(1) = 1
  ...
  Mesh Rotate = 1
End
```

Mortar BC at the sliding interface — **always apply to the rotor side**:
```
Boundary Condition 5     ! sliding_rotor (rotor side, after renumber)
  Target Boundaries(1) = 5
  Name = "SlidingRotor"
  Mortar BC = 3           ! rotational sliding
  Mortar BC Static = 6    ! reference to stator-side boundary
End

Boundary Condition 6     ! sliding_stator (stator side)
  Target Boundaries(1) = 6
  Name = "SlidingStator"
End
```

### 5.4 Transient WhitneyAV with static mesh (Windows-compatible rotation)

**This is the recommended approach for rotating-magnet problems on Windows Elmer.**

For **axisymmetric magnets** (cylinders, rings), rotating the magnetization vector
while keeping the geometry fixed produces the CORRECT external B field.  This is
because the demagnetising field inside a uniformly-magnetised cylinder is
independent of the magnetisation direction (the shape is rotationally symmetric
about Z).

**When this works:**
- The magnet body is rotationally symmetric about the rotation axis
- You only care about fields OUTSIDE the magnet (or the magnet is a cylinder)
- You need eddy currents / forces / torque on external conductive targets

**When it does NOT work:**
- The magnet shape is NOT rotationally symmetric (e.g., rectangular block)
- You need accurate DEMAGNETISING fields inside the magnet at every angle
- You need physical CONTACT between rotating and stationary parts

**Mesh**: Conformal, no rotor domain, no sliding interfaces.  The geometry is
simply `magnet + [target bodies] + air`.  No non-conformal mesh needed.

**SIF structure** — almost identical to steady-state, with these changes:

```
Simulation
  Simulation Type = Transient
  Timestepping Method = BDF
  BDF Order = 1
  Timestep Intervals = $ n_steps
  Timestep Sizes     = $ dt
  ...
End

Solver 1
  Equation = "WhitneyAV"
  Procedure = "MagnetoDynamics" "WhitneyAVSolver"
  Stabilize = True
  Optimize Bandwidth = True
  ...same Windows-safe linear solver settings as steady-state...
  Nonlinear System Max Iterations = 5     ! conductivity adds nonlinearity
  Nonlinear System Convergence Tolerance = 1.0e-06
End

! Magnetization: time-dependent, rotating at ω
Material 1
  Name = "NdFeB_N35"
  Relative Permeability = 1.05
  Magnetization 1 = Variable Time
    Real MATC "955000.0 * cos(2*pi*RPM/60.0 * tx)"
  Magnetization 2 = Variable Time
    Real MATC "955000.0 * sin(2*pi*RPM/60.0 * tx)"
  Magnetization 3 = Real 0.0
End
```

**Timestep selection**: For rotation at frequency f:
- Period T = 1/f.  For 5 Hz: T = 0.2 s.
- Use 40–100 steps per period.  dt = 0.005 s (40 steps) is usually sufficient.
- The conductivity term σ·∂A/∂t adds diagonal dominance → BDF1 is stable.
- The eddy-current time constant for a copper sphere is τ ≈ μ₀σa²/π² ≈ 1.5 ms
  (for a=2.5 cm), so dt = 5 ms is adequate for quasi-DC tracking.

**Beware of long run times**: Transient with nonlinear iterations runs ~5× slower
per step than steady-state.  40 steps at ~20 s/step ≈ 13 minutes.

### 5.5 Force and torque on conductive targets

When a conductive body (copper, aluminum) sits in the rotating magnetic field,
eddy currents are induced → Lorentz force density J×B → net force and torque.

**Mesh setup** (§1.4, §1.5):
- The target body gets its own volume with a separate physical group (e.g., tag 200)
- Include the target surface in the mesh size field source faces for local refinement
- No special BC needed on the target surface (natural BC = E-field continuity)

**SIF additions:**

```
! Copper target material
Material 2
  Name = "Copper"
  Relative Permeability = 1.0
  Electric Conductivity = 5.96e7
End

! CalcFields — nodal forces and current density
Solver 2
  Exec Solver = After Timestep
  ...
  Calculate Nodal Forces = True       ! ← force density at each node
  Calculate Current Density = True    ! ← J (eddy currents)
  ...
End
```

**Post-processing force & torque** (Python with `meshio`):

```python
import meshio
import numpy as np

mesh = meshio.read("results_transient/case_transient_t0040.vtu")
geom_ids = mesh.cell_data["GeometryIds"][0]  # body ID per cell
nodal_force = mesh.point_data["nodal force"]  # shape (n_nodes, 3)
points = mesh.points

# Find nodes of target body (e.g., body ID = 2)
target_cells = mesh.cells[0].data[geom_ids == 2]  # tetra connectivity
target_nodes = np.unique(target_cells.flatten())

# Total force
F_total = nodal_force[target_nodes].sum(axis=0)

# Torque about target centre
r = points[target_nodes] - TARGET_CENTER
f = nodal_force[target_nodes]
Tz = np.sum(r[:,0] * f[:,1] - r[:,1] * f[:,0])  # about Z axis
```

Install meshio: `pip install meshio`.  See `compute_force_torque.py` in the
worked examples for a complete script.

**Expected magnitude** (order-of-magnitude check):
- For a 5 cm copper sphere at 0.5 m from an NdFeB N35 magnet (D=30mm, H=80mm):
  B at sphere ≈ 8.6×10⁻⁵ T, force ≈ 100–200 nN, torque ≈ 2–3×10⁻⁸ N·m
- Force oscillates at **2× rotation frequency** (J×B has B² dependence)
- Torque is approximately **constant** (braking torque, Lenz's law)

---

## Stage 6 — Result output

```
Solver 3
  Exec Solver = After Saving
  Equation = "ResultOutput"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "case"
  Output Format = "Vtu"
  Vtu Format = True
  Binary Output = True
  Discontinuous Bodies = True
  Save Geometry IDs = True
End
```

VTU files open directly in ParaView.  `Discontinuous Bodies = True` prevents
interpolation artefacts at material interfaces.  `Save Geometry IDs = True`
stores the body ID per cell (field name: `GeometryIds`), which is essential
for per-body force/torque post-processing (§5.5).

---

## Stage 7 — ParaView: multi-file animation

### 7.1 PVD file (aggregating scattered VTU files)

When VTU files are saved into separate subdirectories (e.g., one per angle in
a multi-angle scan), ParaView cannot auto-detect them as a time series.  The
solution is a **`.pvd` file** — an XML index that references all VTU files
with their timestep values.

**Python script to generate the PVD** (template):

```python
from pathlib import Path

DT = 0.005  # seconds between frames
pvd_path = Path("mesh/rotate_5Hz.pvd")

lines = ['<?xml version="1.0"?>',
         '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
         '  <Collection>']

for i in range(N_FRAMES):
    vtu_rel = f"results_angle_{i*10:03d}/case_angle_{i*10:03d}_t0001.vtu"
    lines.append(f'    <DataSet timestep="{i*DT:.6f}" group="" part="0" file="{vtu_rel}"/>')

lines.append('  </Collection>')
lines.append('</VTKFile>')
pvd_path.write_text('\n'.join(lines))
```

Open the `.pvd` file in ParaView → all frames appear as a single time series →
**Play** to animate.

**Important**: The `file=` paths in the PVD are **relative to the PVD file location**.
Place the PVD next to the VTU directories (not inside them).

### 7.2 Transient VTU time series

For transient simulations, VTU files are typically named `case_t0001.vtu`,
`case_t0002.vtu`, etc. in a single `results_transient/` directory.  ParaView
can auto-detect these as a time series IF they are in the SAME directory
and follow a numbered pattern.  If they are scattered, use the PVD approach.

---

## Stage 8 — ParaView: force & torque visualization

### 8.1 Glyph for very small vector fields

For fields like `"nodal force"` (~10⁻⁷ N) or `"current density"` (~10⁻¹ A/m²),
the default Glyph Scale Factor (usually 1.0) makes arrows invisible because the
vector magnitudes are tiny compared to the geometry scale.

**Fix**: Manually set **Scale Factor** to a large value:
- `"nodal force"` → Scale Factor = `1000000` (= 10⁶, to show nN-scale forces)
- `"current density"` → Scale Factor = `100` to `1000`

Adjust until arrows are visible but not overwhelming.  Also use
**Glyph Mode → Uniform Spatial Distribution** with Max Points = `2000–5000`
to avoid arrow overcrowding on large meshes.

### 8.2 Field names containing spaces in Calculator

Elmer outputs field names like `"nodal force"`, `"magnetic flux density"`, etc.
with spaces.  ParaView's Calculator filter treats spaces as token separators,
causing `Undefined symbol` errors.

**Fix**: Wrap the field name in quotes (single or double):

```
cross(r_vec, 'nodal force')          ← correct
cross(r_vec, "nodal force")          ← also correct
cross(r_vec, nodal force)            ← WRONG: space breaks parsing
```

### 8.3 Computing torque density with Calculator

Elmer does not output torque directly.  Compute it in ParaView as `r × F`:

**Step 1** — Calculator: compute position vector relative to target centre
```
Result Array Name: r_vec
Expression: coords - (0.5*iHat + 0.0*jHat + 0.0*kHat)
```
(Replace `(0.5, 0.0, 0.0)` with your target centre coordinates.)

**Step 2** — Calculator: compute torque density
```
Result Array Name: torque_density
Expression: cross(r_vec, 'nodal force')
```

**Step 3** — Glyph with Orientation Array = `torque_density` to visualise it.

### 8.4 Clip to isolate the target body

To see fields only near the target:
- **Clip → Sphere**, Center = target centre, Radius = target radius + small margin
- For a 5 cm sphere: Center = `(0.5, 0, 0)`, Radius = `0.03`

Combine with Glyph to visualise eddy currents (use `"current density"` as
orientation) or nodal forces on the target surface.

---

## Debugging checklist

### Gmsh side

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `'int' object is not subscriptable` | Gmsh ≥ 4.13 API change | Use `_vol_tag()` guard (§1.1) |
| Empty physical group | Surface classification wrong | Use Z-extent not centroid (§1.3) |
| Wrong radius identification | Centroid r_xy = 0 for cylinders | Use `surf_radius()` bounding-box half-extent (§1.3) |
| Mesh too coarse/fine | No size field or wrong params | Distance field + Threshold (§1.4) |
| Mesh too coarse at secondary feature | Only one refinement source in src_faces | Add ALL small-feature faces to src_faces (§1.4) |
| `Could not set option 'Mesh.MshFileVersion'` | Set AFTER generate() | Move before `generate(3)`; use `setNumber` not `setString` |

### Elmer side

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No Equations in the system" | Missing `Equation` block | Add `Equation 1 { Active Solvers(...) }` (§4.1) |
| Crash after MGDynAssembly (Windows) | `Use Tree Gauge = True` crashes Elmer 9.0 Windows | Disable tree gauge; use BiCGStabl+ILU0 (§4.2, §4.2.1) |
| BiCGStabL diverges (residual oscillating) | Tree gauge disabled, system near-singular | Switch to BiCGStabl+ILU0+Stabilize (§4.2.1) |
| BiCGStabL breakdown (sigma==NaN) | ILU2 unstable on singular matrix | Switch to ILU0 or ILU1 (§4.2.1) |
| Direct solver crash (Windows) | Direct solver enables tree gauge by default | Don't use direct on Windows; explicit `Use Tree Gauge = False` → singular matrix |
| umf4num: -1.0 (singular matrix) | Direct solver without tree gauge | Not fixable on Windows — use iterative BiCGStabl+ILU0 |
| Body/Boundary mismatch | Used Gmsh tags instead of ElmerGrid renumbered | Read `mesh.names`, update all Target indices (§3.1) |
| Mortar BC not converging | Applied to wrong side | Mortar BC on rotor, `Mortar BC Static` pointing to stator |
| VTU field names mangled in ParaView | Gmsh name strings | Use ASCII-only names in physical groups |
| `Rotr Number`: Unknown specifier | Elmer 9.0 Windows lacks RigidMeshMapper | Use transient static-mesh approach instead (§5.4) |
| Transient WhitneyAV diverges at step 1 | Initial condition A=0 with strong M | Add `Nonlinear System Max Iterations = 5`; reduce dt |
| Transient WhitneyAV runs very slowly | Nonlinear iterations per step too many | Reduce to 3; check if `Steady State Convergence Tolerance` was left on |
| Nodal force field all zero in VTU | `Calculate Nodal Forces` not set in CalcFields | Add `Calculate Nodal Forces = True` to CalcFields solver (§5.5) |
| Zero magnetization → trivial solution | `Real 955000.0` syntax error | Use plain `955000.0` without `Real` prefix (§4.4) |

### ParaView side

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Undefined symbol: 'nodalforce'` in Calculator | Field name has a space: `nodal force` | Use quotes: `'nodal force'` (§8.2) |
| Glyph arrows invisible | Scale Factor too small for nano-scale fields | Set Scale Factor = 1e6 (§8.1) |
| Glyph arrows too dense (crashes ParaView) | Too many points | Use Uniform Spatial Distribution, Max Points ~2000 (§8.1) |
| Cannot play animation from scattered VTU files | Files in separate subdirectories | Generate a .pvd index file (§7.1) |
| "ResultOutputSolver instance already exists" warning | Duplicate VTU output from calc + output solver | Harmless; ignore |
| Wanted torque but no torque field exists | Elmer does not output torque natively | Use Calculator: `cross(r_vec, 'nodal force')` (§8.3) |

---

## Reference files

This skill is distributed with worked examples — a static diametrical NdFeB permanent
magnet (`static_magnet/`) and a rotating PM multi-angle scan (`rotating_magnet/`).

**Expanded examples** (shipped alongside in the repository):
- `static_magnet/` — Steady-state magnet simulation with conformal mesh (0.5 m box)
- `rotating_magnet/` — Multi-angle quasi-static rotation scan (36 angles, 5 Hz, 0.5 m box)
- `SingleSolidMagnetFEA/` — Complete steady-state magnet simulation with conformal mesh
- `SingleRotateMagnetFEA/` — Production-scale rotation scan (5 m box, 36 angles, 5 Hz)
- `SingleRotateMagnetTinyTargetFEA/` — Transient rotating magnet + copper sphere force/torque computation

See `prompt.md` for ready-to-run Claude Code prompts that exercise each scenario.
