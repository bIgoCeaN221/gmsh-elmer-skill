---
name: gmsh-elmer
description: >
  End-to-end Gmsh → Elmer FEM workflow for electromagnetic and rotating-machinery problems.
  Use this skill whenever the user needs to: generate a 3D mesh with Gmsh for Elmer,
  create Elmer SIF solver-input files, set up WhitneyAV / magnetostatic / rotating
  simulations, or debug Gmsh-to-Elmer pipeline issues.  Triggers on mentions of "Gmsh
  + Elmer", "mesh for Elmer", "ElmerGrid", "case.sif", "RigidMeshMapper", "WhitneyAV",
  "magnetostatics mesh", "rotating machinery FEM", "electromagnetic simulation mesh",
  or any request to go from CAD/geometry to Elmer solver.
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

---

## Stage 5 — Rotation / rotating machinery

### 5.1 Two approaches

| Approach | Mesh | Solver | Use case |
|----------|------|--------|----------|
| Multi-angle steady-state | Conformal | WhitneyAV only | Magnetostatics, no eddy currents |
| Transient RigidMeshMapper | Non-conformal | RigidMeshMapper + WhitneyAV | Full transient, eddy currents |

### 5.2 Multi-angle scan (simpler, robust)

Run steady-state at N discrete angles.  Magnetization direction at angle θ:
```
Mx(θ) = M₀·cos(θ),   My(θ) = M₀·sin(θ)
```

Generate one SIF per angle, changing only the `Magnetization 1/2` values.
A Python script can batch-generate these (see the `rotate_scan.py` pattern).

### 5.3 Transient RigidMeshMapper (full physics)

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
interpolation artefacts at material interfaces.

---

## Debugging checklist

### Gmsh side

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `'int' object is not subscriptable` | Gmsh ≥ 4.13 API change | Use `_vol_tag()` guard (§1.1) |
| Empty physical group | Surface classification wrong | Use Z-extent not centroid (§1.3) |
| Wrong radius identification | Centroid r_xy = 0 for cylinders | Use `surf_radius()` bounding-box half-extent (§1.3) |
| Mesh too coarse/fine | No size field or wrong params | Distance field + Threshold (§1.4) |
| `Could not set option 'Mesh.MshFileVersion'` | Set AFTER generate() | Move before `generate(3)`; use `setNumber` not `setString` |

### Elmer side

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No Equations in the system" | Missing `Equation` block | Add `Equation 1 { Active Solvers(...) }` (§4.1) |
| Crash after MGDynAssembly (Windows) | `Use Tree Gauge = True` crashes Elmer 9.0 Windows | Disable tree gauge; use GMRES+ILU0 (§4.2, §4.2.1) |
| BiCGStabL diverges (residual oscillating) | Tree gauge disabled, system near-singular | Switch to GMRES+ILU0 (§4.2.1) |
| BiCGStabL breakdown (sigma==NaN) | ILU2 unstable on singular matrix | Switch to ILU0 or ILU1 (§4.2.1) |
| Direct solver crash (Windows) | Direct solver enables tree gauge by default | Don't use direct on Windows; explicit `Use Tree Gauge = False` → singular matrix |
| umf4num: -1.0 (singular matrix) | Direct solver without tree gauge | Not fixable on Windows — use iterative GMRES+ILU0 |
| Body/Boundary mismatch | Used Gmsh tags instead of ElmerGrid renumbered | Read `mesh.names`, update all Target indices (§3.1) |
| Mortar BC not converging | Applied to wrong side | Mortar BC on rotor, `Mortar BC Static` pointing to stator |
| VTU field names mangled in ParaView | Gmsh name strings | Use ASCII-only names in physical groups |

---

## Reference files

This skill is distributed with a worked example in `TEST/` — a diametrical NdFeB
permanent magnet simulation.  See `prompt.md` for a ready-to-run Claude Code prompt
that exercises the full Gmsh→Elmer→ParaView pipeline using the test data.
