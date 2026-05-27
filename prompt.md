# Quick-start prompts

After installing the `gmsh-elmer` skill, copy any prompt below into Claude Code to run the corresponding workflow. Each prompt assumes the skill is installed — Claude Code will follow the skill patterns automatically.

---

## Prompt 1 — Static magnet (`static_magnet/`)

```
使用static_magnet文件夹下的magnet_mesh.py生成Gmsh网格，然后用ElmerGrid转换成Elmer格式，再用static_magnet文件夹下的case_steady.sif运行ElmerSolver进行稳态求解。求解完成后，用ParaView打开VTU结果，按照README里裁剪±4cm区域的步骤来设置Glyph可视化，验证磁感应强度B的偶极场分布。
```

**Expected:** Generates mesh, runs ElmerSolver, confirms non-zero B field, guides ParaView visualization.

---

## Prompt 2 — Rotating magnet: multi-angle quasi-static scan

```
在SingleRotateMagnetFEA文件夹下进行旋转永磁体仿真。永磁体旋转频率5Hz。
用Gmsh Python脚本生成旋转磁铁网格（圆柱磁铁r=15mm h=80mm NdFeB，带转子铁芯r=25mm h=120mm，外部空气域边长5m）。
生成36个稳态SIF文件，每个对应一个旋转角度（0°到350°，步长10°）。
每个SIF中磁化方向: Mx = M0*cos(θ), My = M0*sin(θ)，其中M0=955000 A/m。
逐个用ElmerSolver求解所有36个角度。
生成PVD文件聚合所有VTU结果，使ParaView可以连续播放。
在ParaView中打开PVD文件，用Clip+Glyph显示旋转磁场动画。
```

**Expected:** 36 steady-state solves, PVD aggregation, animated rotating dipole field in ParaView.

---

## Prompt 3 — Rotating magnet (`rotating_magnet/` in-repo example)

```
使用rotating_magnet文件夹下的算例运行旋转永磁体仿真。
1. 用magnet_mesh.py生成Gmsh网格
2. ElmerGrid转换成Elmer格式
3. 用rotate_scan.py生成36个角度的SIF文件
4. 逐个求解所有36个角度
5. 用create_pvd.py生成ParaView动画文件
6. 在ParaView中打开.pvd文件，用Clip+Glyph显示旋转磁场动画
```

**Expected:** Same as Prompt 2 but using the in-repo 0.5 m box example — much faster to run as a demo.

---

## Prompt 4 — Copper sphere: transient force & torque

```
在SingleRotateMagnetTinyTargetFEA文件夹下进行仿真。
原点处旋转永磁体（r=15mm h=80mm NdFeB，转子r=25mm h=120mm，5Hz旋转）。
在(0.5m, 0, 0)处放置直径5cm的铜球（电导率5.96e7 S/m）。
Gmsh建模→ElmerGrid转换→Elmer瞬态求解。

Elmer设置：
- WhitneyAV瞬态求解器（BDF Order=1，40步/周期，dt=0.005s）
- 时变磁化：Mx(t)=M0*cos(ωt), My(t)=M0*sin(ωt)，M0=955000, ω=2π*5 rad/s
- CalcFields启用Calculate Nodal Forces和Calculate Current Density
- 输出Discontinuous Bodies=True, Save Geometry IDs=True
- Windows兼容设置：BiCGStabl+ILU0+Stabilize=True，不用Tree Gauge

求解后用meshio提取VTU中GeometryIds=2（铜球）的nodal force，计算总力与力矩（对球心(0.5,0,0)取矩），输出force_torque.csv和力/力矩随时间变化图。
在ParaView中可视化铜球表面的nodal force矢量（Glyph Scale Factor=1000000）。
```

**Expected:** 40-timestep transient solve, force/torque CSV and plots, ParaView force glyphs on copper sphere.

---

## Prompt 5 — Static magnet with custom parameters

```
参照static_magnet文件夹下的算例，对以下永磁体进行静磁仿真：
- 形状：圆柱，半径____mm，高度____mm
- 材料：NdFeB N35，剩磁____T（对应M0=____A/m）
- 充磁方向：____向（如径向/轴向）
- 外部空气域边长____m

从Gmsh建模开始，到Elmer稳态求解，最后ParaView看B场分布。
```

**Expected:** Adapted mesh and SIF for custom magnet dimensions, same pipeline.

---

## Expected flow (all prompts)

Claude Code with the skill installed will:

1. Generate Gmsh mesh via Python script
2. Run `ElmerGrid 14 2 mesh.msh -out mesh2 -autoclean` to convert
3. Generate/copy `.sif` files and run `ElmerSolver`
4. Verify results are physically reasonable (non-zero B, expected symmetry)
5. Generate PVD files when needed for multi-file animation
6. Provide ParaView steps or post-processing scripts

## Manual execution (without Claude Code)

### Static magnet

```bash
cd static_magnet
python magnet_mesh.py
ElmerGrid 14 2 mesh.msh -out mesh2 -autoclean
cp case_steady.sif mesh2/
cd mesh2
ElmerSolver case_steady.sif
start results/case_t0001.vtu
```

Or on Windows, double-click `static_magnet/run_steady.bat`.

### Rotating magnet (in-repo example)

```bash
cd rotating_magnet
python magnet_mesh.py
ElmerGrid 14 2 mesh.msh -out mesh -autoclean
cp case_rotate.sif mesh/
cd mesh
ElmerSolver case_rotate.sif              # single angle test
cd ..
python rotate_scan.py                     # generates all 36 SIFs
cd mesh && run_all_angles.bat && cd ..    # run all 36 solves
python create_pvd.py                      # generate ParaView animation
start rotate_animation.pvd
```

Or on Windows, double-click `rotating_magnet/run_rotate.bat` (full pipeline).

```bash
cd SingleRotateMagnetFEA
python magnet_mesh.py
python rotate_scan.py          # generates 36 SIF files
# Run each angle (example for 0°):
ElmerGrid 14 2 mesh.msh -out magnet_mesh_angle_000 -autoclean
cp case_angle_000.sif magnet_mesh_angle_000/
cd magnet_mesh_angle_000 && ElmerSolver case_angle_000.sif && cd ..
# ... repeat for all 36 angles ...
python create_pvd.py           # generate animation.pvd
start animation.pvd
```

### Copper sphere force/torque

```bash
cd SingleRotateMagnetTinyTargetFEA
python magnet_target_mesh.py
ElmerGrid 14 2 mesh.msh -out magnet_mesh -autoclean
cp case_transient.sif magnet_mesh/
cd magnet_mesh
ElmerSolver case_transient.sif
cd ..
pip install meshio
python compute_force_torque.py  # extracts force/torque, generates CSV and plots
python plot_force_torque.py     # alternative: plot from CSV
```
