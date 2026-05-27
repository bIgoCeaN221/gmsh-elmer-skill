# gmsh-elmer — Claude Code 技能

端到端 **Gmsh → Elmer FEM** 工作流技能，用于 Claude Code。覆盖电磁场与旋转机械仿真：几何建模、网格划分、ElmerGrid 转换、求解器输入（WhitneyAV、静磁、瞬态旋转、力/力矩计算）、ParaView 可视化（PVD 时间序列、力矢量箭头）以及常见故障排查。

## 安装

```bash
# 克隆仓库
git clone git@github.com:bIgoCeaN221/gmsh-elmer-skill.git

# 安装技能到 Claude Code
# 方式 A：注册为用户技能
mkdir -p ~/.claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md ~/.claude/skills/gmsh-elmer/

# 方式 B：注册为项目技能（在项目根目录下）
mkdir -p .claude/skills/gmsh-elmer
cp gmsh-elmer-skill/SKILL.md .claude/skills/gmsh-elmer/
```

重启 Claude Code（或打开新会话）— 当你提到 Gmsh、Elmer、WhitneyAV、静磁网格、旋转机械、力/力矩计算、PVD 动画等关键词时，技能会自动加载。

## 技能覆盖范围

| 阶段 | 工具 | 内容 |
|------|------|------|
| 几何建模 | Gmsh (OpenCASCADE) | 布尔运算、表面分类、共形/非共形界面 |
| 网格划分 | Gmsh | 距离场网格尺寸控制、物理组、Elmer v2.2 导出 |
| 格式转换 | ElmerGrid | 重新编号规则、`-autoclean` 标志 |
| 求解器 | ElmerSolver | WhitneyAV、CalcFields、RigidMeshMapper、Mortar BC |
| 瞬态旋转 | ElmerSolver | 时变磁化强度 MATC 表达式、静态网格方案（兼容 Windows） |
| 力与力矩 | ElmerSolver + meshio | `Calculate Nodal Forces`、GeometryIds 过滤、叉积力矩 |
| 多文件动画 | ParaView | PVD XML 聚合分散的 VTU 目录 |
| 力矢量可视化 | ParaView | 纳牛级矢量缩放、Calculator 引号规则、力矩密度 |
| 故障排查 | — | Windows 下 Tree Gauge 崩溃、BiCGStabl vs BiCGStabL、`Real` 关键字陷阱 |

## 仓库示例

本仓库包含两个完整可运行的示例：

### `static_magnet/` — 静态 NdFeB 永磁体

径向充磁 NdFeB 圆柱（直径 30 mm，高 80 mm）在 0.5 m 空气域中。稳态 WhitneyAV 求解。最简单的入门示例。

```
static_magnet/
├── magnet_mesh.py       ← Gmsh 网格生成脚本
├── case_steady.sif      ← Elmer 求解器输入文件
├── run_steady.bat        ← Windows 一键运行批处理
├── mesh.msh              ← 预生成的网格文件（约 3 MB）
└── results/
    └── case_t0001.vtu    ← 样本 VTU 结果
```

### `rotating_magnet/` — 旋转永磁体（多角度准静态扫描）

与静态示例相同的几何模型，但磁化方向旋转。生成 36 个稳态 SIF 文件（0°–350°），逐个求解，然后聚合成 ParaView PVD 动画。演示了无需 RigidMeshMapper 的 Windows 兼容旋转方案。

```
rotating_magnet/
├── magnet_mesh.py       ← 与静态示例相同的网格生成器
├── case_rotate.sif      ← 示例 SIF 文件（角度 0°）
├── rotate_scan.py       ← 生成 36 个 SIF 文件 + 批处理脚本
├── create_pvd.py        ← PVD 动画文件生成器
├── run_rotate.bat        ← Windows 一键运行流程
├── mesh.msh              ← 预生成的网格文件（约 3 MB）
└── results/
    └── case_angle_000_t0001.vtu  ← 样本 VTU（角度 0°）
```

两个示例使用相同的网格；安装技能后，从 `prompt.md` 复制提示词到 Claude Code 即可运行任一流程。

## 相关项目

- **`SingleRotateMagnetFEA/`** — 大尺寸旋转磁铁（5 m 空气域，300 RPM，36 角度）。与 `rotating_magnet/` 相同技术，但使用生产级尺寸。
- **`SingleRotateMagnetTinyTargetFEA/`** — 瞬态 WhitneyAV 仿真，在 (0.5, 0, 0) 处有铜球（直径 5 cm）。时变磁化强度在铜球中感应涡流；CalcFields 计算节点力；meshio 后处理提取力和力矩随时间变化。

## 使用本技能的示例项目

除 `TEST/` 外，上级仓库包含两个完整示例：

- **`SingleRotateMagnetFEA/`** — 多角度准静态旋转扫描（36 个角度，0°–350°）。每个角度执行稳态 WhitneyAV 求解，通过 PVD 聚合实现 ParaView 动画。演示了无需 RigidMeshMapper 的时变磁化方案（Windows 兼容）。
- **`SingleRotateMagnetTinyTargetFEA/`** — 瞬态 WhitneyAV 仿真，在 (0.5, 0, 0) 处有一个铜球（直径 5 cm）。时变磁化强度在铜球中感应出涡流；CalcFields 计算节点力；meshio 后处理提取总力和力矩随时间变化曲线。

## 依赖环境

- [Gmsh](https://gmsh.info/) ≥ 4.13（Python API：`pip install gmsh`）
- [Elmer FEM](https://www.csc.fi/web/elmer) 9.0
- [ParaView](https://www.paraview.org/) ≥ 5.10（可视化）
- [meshio](https://github.com/nschloe/meshio) ≥ 5.0（Python：`pip install meshio` — 用于 VTU 力/力矩后处理）

## ParaView 快速检查

仿真运行后，在 ParaView 中打开 `static_magnet/results/case_t0001.vtu`。要看到偶极场图案（而非平行箭头）：

1. **File → Open** `case_t0001.vtu` → 点击 **Apply**
2. 添加 **Clip** 滤波器：Box，`[-0.04, -0.04, -0.04]` 到 `[0.08, 0.08, 0.08]`，勾选 **Invert**
3. 添加 **Glyph** 滤波器：Orientation = `magnetic flux density`，Scale Factor = `0.015`

裁剪到磁铁区域（±4 cm），即可看到被远场箭头淹没的偶极场分布。

要查看**更大范围**的磁场，增大 Clip 包围盒尺寸（如 `[-0.15, -0.15, -0.15]` 到 `[0.20, 0.20, 0.20]`）。Clip + Glyph 方案适用于任意范围——根据需要调整包围盒即可。

## ParaView：多文件动画（PVD）

当 VTU 文件分散在不同的子目录中（如每个旋转角度或时间步一个目录），ParaView 无法自动将其作为时间序列播放。生成 `.pvd` XML 集合文件：

```python
# create_pvd.py
from pathlib import Path

N_STEPS = 36
DT = 1.0 / 180.0  # 示例

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

在 ParaView 中打开 `.pvd` 文件——所有 VTU 文件将作为单一时间序列出现，支持播放控制。

## ParaView：力与力矩可视化

对于启用了 `Calculate Nodal Forces = True` 的仿真，VTU 输出包含 `nodal force` 点数据场。由于数值非常小（~10⁻⁷ N），可视化时需要特殊处理。

**力矢量箭头（Glyph）：**
1. 打开 VTU → **Apply**
2. 添加 **Glyph** 滤波器
3. 设置 **Orientation Array** = `nodal force`，**Scale Array** = `nodal force`
4. 设置 **Scale Factor** = `1000000`（场值量级为 ~10⁻⁷ N，默认缩放比例无法显示箭头）
5. 根据需要设置 **Glyph Type** 为 Arrow 或 3D Glyph

**在 ParaView Calculator 中计算力矩：**
1. 应用 **Calculator** 滤波器
2. 计算相对于旋转中心的位置向量，如：`coords - (0.5, 0.0, 0.0)`
3. 再次应用 **Calculator** 计算力矩密度：`cross(r_vec, 'nodal force')`
   - 带空格的场名（如 `nodal force`）在表达式中必须用**单引号**括起来
4. 结果为每个节点的力矩密度（N·m）

**特定物体的受力：** 使用 **Threshold** 滤波器对 `GeometryIds` 进行筛选，隔离目标物体，然后仅查看其节点上的 `nodal force`。

## 本技能记录的关键修复

- **`Real` 关键字陷阱** — `Magnetization 1 = Real 955000.0` 会静默置零
- **Tree Gauge 崩溃** — Elmer 9.0 Windows 在构建 Gauge Tree 时崩溃
- **BiCGStabl vs BiCGStabL** — Windows 上 BiCGStabL + ILU0 发散；BiCGStabl 可用
- **GMRES 虚假收敛** — RHS 非零时收敛到平凡解 A=0
- **表面分类** — 用包围盒 Z 向跨度而非形心
- **ElmerGrid 重新编号** — 标签从 1 开始顺序重排
- **Windows 无 RigidMeshMapper 模块** — Elmer 9.0 Windows 版本缺少该模块；改用瞬态 WhitneyAV + 时变磁化强度 + 静态网格方案
- **ParaView Calculator 中 `nodal force` 的引号规则** — 带空格的场名必须用单引号：`'nodal force'`
- **纳牛级矢量无法显示箭头** — 手动设置 Scale Factor（如 ~10⁻⁷ N 的场设置为 1,000,000）

## 许可证

MIT
