# Quick-start prompt

After installing the `gmsh-elmer` skill, copy the text below into Claude Code to run the full pipeline with the test data in `TEST/`.

---

## Prompt (copy from here)

```
使用TEST文件夹下的magnet_mesh.py生成Gmsh网格，然后用ElmerGrid转换成Elmer格式，再用TEST文件夹下的case_steady.sif运行ElmerSolver进行稳态求解。求解完成后，用ParaView打开VTU结果，按照README里裁剪±4cm区域的步骤来设置Glyph可视化，验证磁感应强度B的偶极场分布。
```

---

## Expected flow

Claude Code with the skill installed will:

1. Run `python TEST/magnet_mesh.py` to generate `mesh.msh`
2. Run `ElmerGrid 14 2 mesh.msh -out mesh2 -autoclean` to convert
3. Copy `TEST/case_steady.sif` into `mesh2/` and run `ElmerSolver`
4. Confirm B field is non-zero and dipole pattern is present
5. Provide ParaView steps (or auto-run with `pvpython`)

## Manual execution (without Claude Code)

If you prefer to run without Claude Code:

```bash
# 1. Generate mesh
cd TEST
python magnet_mesh.py

# 2. Convert for Elmer
ElmerGrid 14 2 mesh.msh -out mesh2 -autoclean

# 3. Copy SIF and solve
cp case_steady.sif mesh2/
cd mesh2
ElmerSolver case_steady.sif

# 4. Open results in ParaView
start results/case_t0001.vtu
```

Or on Windows, simply double-click `TEST/run_steady.bat`.
