# gmsh-elmer — Claude Code 技能

端到端 **Gmsh → Elmer FEM** 工作流技能，用于 Claude Code。覆盖电磁场与旋转机械仿真：几何建模、网格划分、ElmerGrid 转换、求解器输入（WhitneyAV、静磁、瞬态旋转）以及常见故障排查。

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

重启 Claude Code（或打开新会话）— 当你提到 Gmsh、Elmer、WhitneyAV、静磁网格、旋转机械等关键词时，技能会自动加载。

## 技能覆盖范围

| 阶段 | 工具 | 内容 |
|------|------|------|
| 几何建模 | Gmsh (OpenCASCADE) | 布尔运算、表面分类、共形/非共形界面 |
| 网格划分 | Gmsh | 距离场网格尺寸控制、物理组、Elmer v2.2 导出 |
| 格式转换 | ElmerGrid | 重新编号规则、`-autoclean` 标志 |
| 求解器 | ElmerSolver | WhitneyAV、CalcFields、RigidMeshMapper、Mortar BC |
| 故障排查 | — | Windows 下 Tree Gauge 崩溃、BiCGStabl vs BiCGStabL、`Real` 关键字陷阱 |

## 快速测试

`TEST/` 目录包含一个完整的验证算例 — 径向充磁 NdFeB 永磁体仿真。安装技能后，将 `prompt.md` 中的提示词复制到 Claude Code 中即可运行完整流程。

```
TEST/
├── magnet_mesh.py       ← Gmsh 网格生成脚本
├── case_steady.sif      ← Elmer 求解器输入文件
├── run_steady.bat        ← Windows 一键运行批处理
├── mesh.msh              ← 预生成的网格文件（约 3 MB）
└── results/
    └── case_t0001.vtu    ← 样本 VTU 结果（约 4 MB）
```

## 依赖环境

- [Gmsh](https://gmsh.info/) ≥ 4.13（Python API：`pip install gmsh`）
- [Elmer FEM](https://www.csc.fi/web/elmer) 9.0
- [ParaView](https://www.paraview.org/) ≥ 5.10（可视化）

## ParaView 快速检查

仿真运行后，在 ParaView 中打开 `TEST/results/case_t0001.vtu`。要看到偶极场图案（而非平行箭头）：

1. **File → Open** `case_t0001.vtu` → 点击 **Apply**
2. 添加 **Clip** 滤波器：Box，`[-0.04, -0.04, -0.04]` 到 `[0.08, 0.08, 0.08]`，勾选 **Invert**
3. 添加 **Glyph** 滤波器：Orientation = `magnetic flux density`，Scale Factor = `0.015`

裁剪到磁铁区域（±4 cm），即可看到被远场箭头淹没的偶极场分布。

## 本技能记录的关键修复

- **`Real` 关键字陷阱** — `Magnetization 1 = Real 955000.0` 会静默置零
- **Tree Gauge 崩溃** — Elmer 9.0 Windows 在构建 Gauge Tree 时崩溃
- **BiCGStabl vs BiCGStabL** — Windows 上 BiCGStabL + ILU0 发散；BiCGStabl 可用
- **GMRES 虚假收敛** — RHS 非零时收敛到平凡解 A=0
- **表面分类** — 用包围盒 Z 向跨度而非形心
- **ElmerGrid 重新编号** — 标签从 1 开始顺序重排

## 许可证

MIT
