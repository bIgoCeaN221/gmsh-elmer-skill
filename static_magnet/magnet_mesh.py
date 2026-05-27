"""
Gmsh mesh generator — diametrical PM cylinder in air box.
Conformal mesh with sliding interface for future rotation support.
"""
import sys
import gmsh

# ── Parameters ───────────────────────────────────────────────────
MAGNET_R  = 0.015      # 15 mm radius
MAGNET_H  = 0.080      # 80 mm height
BOX_HALF  = 0.25       # 250 mm half-box (0.5m total)
ROTOR_R   = 0.025      # rotating air cylinder radius

LC_MAGNET  = 0.003     # 3 mm on magnet surface
LC_ROTOR   = 0.006     # 6 mm at rotor interface
LC_BOX     = 0.080      # 80 mm at far-field

# ── Prepare ───────────────────────────────────────────────────────
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
gmsh.model.add("magnet_mesh")

# ── Geometry (OCC) ────────────────────────────────────────────────
def _tag(r):
    """Extract first volume tag from Gmsh OCC return (handles 4.13+ API)."""
    if isinstance(r, int):
        return r
    # cut/fuse returns (outDimTags, outDimTagsMap)
    # outDimTags is list of (dim,tag) or list of int
    first = r[0]
    if isinstance(first, (list, tuple)):
        if len(first) == 0:
            raise ValueError("Empty result from OCC operation")
        first = first[0]
    if isinstance(first, (tuple,)):
        return first[1]  # (dim, tag)
    return first

# Air box
box = gmsh.model.occ.addBox(-BOX_HALF, -BOX_HALF, -BOX_HALF,
                            2*BOX_HALF, 2*BOX_HALF, 2*BOX_HALF)
box_tag = _tag(box)

# Rotor cylinder
rotor = gmsh.model.occ.addCylinder(0, 0, -BOX_HALF, 0, 0, 2*BOX_HALF, ROTOR_R)
rotor_tag = _tag(rotor)

# Magnet cylinder
mag = gmsh.model.occ.addCylinder(0, 0, -MAGNET_H/2, 0, 0, MAGNET_H, MAGNET_R)
mag_tag = _tag(mag)

# Boolean: box - rotor → stationary air (remove box, KEEP rotor)
stationary = gmsh.model.occ.cut([(3, box_tag)], [(3, rotor_tag)],
                                removeObject=True, removeTool=False)
stat_tag = _tag(stationary)

# Boolean: rotor - magnet → rotating air (remove rotor, KEEP magnet)
rotating = gmsh.model.occ.cut([(3, rotor_tag)], [(3, mag_tag)],
                               removeObject=True, removeTool=False)
rot_tag = _tag(rotating)

gmsh.model.occ.synchronize()

# ── Surface classification ────────────────────────────────────────
def classify_cyl_surfaces(vol_tag):
    surfs_data = gmsh.model.getBoundary([(3, vol_tag)], combined=False)
    surfs = [s[1] for s in surfs_data]
    result = {"top": [], "bot": [], "side": [], "other": []}
    for s in surfs:
        bbox = gmsh.model.getBoundingBox(2, s)
        z_ext = bbox[5] - bbox[2]
        cz = (bbox[2] + bbox[5]) / 2
        if z_ext < 1e-4:          # flat → cap
            if cz > MAGNET_H/2 - 1e-3:
                result["top"].append(s)
            elif cz < -MAGNET_H/2 + 1e-3:
                result["bot"].append(s)
            else:
                result["other"].append(s)
        else:                      # tall → side wall
            result["side"].append(s)
    return result

def surf_radius(surf_tag):
    bbox = gmsh.model.getBoundingBox(2, surf_tag)
    rx = (bbox[3] - bbox[0]) / 2
    ry = (bbox[4] - bbox[1]) / 2
    return max(rx, ry)

# Classify magnet surfaces
mag_faces = classify_cyl_surfaces(mag_tag)

# Classify rotor-air surfaces (after magnet cut)
rot_faces = classify_cyl_surfaces(rot_tag)

# Identify inner/outer side walls by radius
all_side = rot_faces["side"][:]
inner_walls = []
outer_walls = []
for s in all_side:
    r = surf_radius(s)
    if r < MAGNET_R + 0.001:
        inner_walls.append(s)
    else:
        outer_walls.append(s)

# Classify stationary air surfaces (box interior minus rotor hole)
stat_surfs_data = gmsh.model.getBoundary([(3, stat_tag)], combined=False)
stat_surfs = [s[1] for s in stat_surfs_data]

# Far-field = faces of the box (at x,y,z = ±BOX_HALF)
far_field = []
for s in stat_surfs:
    bbox = gmsh.model.getBoundingBox(2, s)
    cx = (bbox[0] + bbox[3]) / 2
    cy = (bbox[1] + bbox[4]) / 2
    cz = (bbox[2] + bbox[5]) / 2
    x_ext = bbox[3] - bbox[0]
    y_ext = bbox[4] - bbox[1]
    z_ext = bbox[5] - bbox[2]
    # Box face has large extent in 2 directions, thin in 1
    if x_ext > BOX_HALF*0.9 and y_ext > BOX_HALF*0.9 and z_ext < 1e-4:
        far_field.append(s)
    elif x_ext > BOX_HALF*0.9 and z_ext > BOX_HALF*0.9 and y_ext < 1e-4:
        far_field.append(s)
    elif y_ext > BOX_HALF*0.9 and z_ext > BOX_HALF*0.9 and x_ext < 1e-4:
        far_field.append(s)

# The cylindrical hole in stationary air = stator-side sliding interface
stator_hole = []
for s in stat_surfs:
    if s not in far_field:
        bbox = gmsh.model.getBoundingBox(2, s)
        z_ext = bbox[5] - bbox[2]
        if z_ext > 1e-4:  # tall → cylindrical hole wall
            stator_hole.append(s)

# ── Mesh size fields ──────────────────────────────────────────────
# Distance-based: fine near magnet, coarser toward far-field
src_faces = [mag_faces["side"][0]] if mag_faces["side"] else []
src_faces += mag_faces["top"] + mag_faces["bot"]

gmsh.model.mesh.field.add("Distance", 1)
gmsh.model.mesh.field.setNumbers(1, "FacesList", src_faces)

gmsh.model.mesh.field.add("Threshold", 2)
gmsh.model.mesh.field.setNumber(2, "InField", 1)
gmsh.model.mesh.field.setNumber(2, "SizeMin", LC_MAGNET)
gmsh.model.mesh.field.setNumber(2, "SizeMax", LC_BOX)
gmsh.model.mesh.field.setNumber(2, "DistMin", 0.005)
gmsh.model.mesh.field.setNumber(2, "DistMax", 0.350)

gmsh.model.mesh.field.add("Min", 3)
gmsh.model.mesh.field.setNumbers(3, "FieldsList", [2])
gmsh.model.mesh.field.setAsBackgroundMesh(3)

# ── Physical groups ───────────────────────────────────────────────
# Bodies (for ElmerGrid renumbering: 100->1, 200->2, 300->3)
gmsh.model.addPhysicalGroup(3, [mag_tag],  tag=100, name="magnet")
gmsh.model.addPhysicalGroup(3, [rot_tag],  tag=200, name="air_rotating")
gmsh.model.addPhysicalGroup(3, [stat_tag], tag=300, name="air_stationary")

# Boundaries (for ElmerGrid renumbering: 10->1, 11->2, ...)
gmsh.model.addPhysicalGroup(2, far_field,   tag=10, name="far_field")
gmsh.model.addPhysicalGroup(2, mag_faces["top"], tag=11, name="mag_top")
gmsh.model.addPhysicalGroup(2, mag_faces["bot"], tag=12, name="mag_bot")
gmsh.model.addPhysicalGroup(2, mag_faces["side"], tag=13, name="mag_side")
gmsh.model.addPhysicalGroup(2, outer_walls, tag=20, name="sliding_rotor")
if stator_hole:
    gmsh.model.addPhysicalGroup(2, stator_hole, tag=21, name="sliding_stator")

# ── Mesh options ──────────────────────────────────────────────────
gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
gmsh.option.setNumber("Mesh.Algorithm3D", 1)      # Delaunay
gmsh.option.setNumber("Mesh.Optimize", 1)
gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)
gmsh.option.setNumber("Mesh.ElementOrder", 1)      # linear

# ── Generate ──────────────────────────────────────────────────────
gmsh.model.mesh.generate(3)

# ── Validate ──────────────────────────────────────────────────────
print("\n── Physical group check ──")
for dim, ptag in gmsh.model.getPhysicalGroups():
    ents = gmsh.model.getEntitiesForPhysicalGroup(dim, ptag)
    name = gmsh.model.getPhysicalName(dim, ptag)
    count = len(ents)
    status = "OK" if count > 0 else "EMPTY!"
    print(f"  {status:7s} dim={dim} tag={ptag:3d} '{name}': {count} entities")

# ── Export ────────────────────────────────────────────────────────
gmsh.write("mesh.msh")    # v2.2 for ElmerGrid
gmsh.write("magnet.msh")  # v4 for Gmsh GUI

print("\n── Mesh stats ──")
nodes = gmsh.model.mesh.getNodes()
nnodes = nodes[0].size
print(f"  Nodes: {nnodes}")
print("  Done.")

gmsh.finalize()
