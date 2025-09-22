# render_views.py 使用说明与实现原理

本文件记录 `benchmark/render_views.py` 的实现原理、运行步骤、参数说明与故障排查，目标是从仓库中的 STEP CAD 模型生成六个标准视图：`front/back/left/right/top/bottom`。

## 实现原理（步骤）

1. STEP -> STL（Mesh）转换（使用 FreeCADCmd）
   - 脚本在临时目录生成一个小的 FreeCAD Python 脚本并通过 `FreeCADCmd.exe` 执行。
   - 在 FreeCAD 脚本中，尝试以下方式读取 STEP：
     - `Import.open(infile)` 并 `Mesh.export(objs, outfile)`；
     - 如果失败，则创建新文档（`FreeCAD.newDocument()`或`App.newDocument()`），调用 `Import.open(infile, doc.Name)` 再 `Mesh.export(doc.Objects, outfile)`。
   - 生成的临时 STL 会被复制到 STEP 文件所在目录，命名为 `<sample>.stl`。

2. STL -> 图像渲染
   - 脚本尝试使用 `trimesh` 来加载 STL 并调用 `Scene.save_image()` 生成 PNG（此方法能产生较好的带光照的图像，但依赖 `pyglet`，在无 GUI 或未安装 `pyglet` 时可能失败）。
   - 若 `trimesh` 的 `save_image()` 不可用或失败，脚本使用 `matplotlib`（`mpl_toolkits.mplot3d`）的 `plot_trisurf` 离线渲染替代。虽然不能做复杂光照，但在无头环境下可用且快速。
   - 为每个视图设置固定的相机参数（elev/azim）：
     - front: (0, 0)
     - back: (0, 180)
     - left: (0, 90)
     - right: (0, -90)
     - top: (90, 0)
     - bottom: (-90, 0)

3. 输出
   - 各视图保存为同目录下的 `<sample>_front.png`、`<sample>_back.png` 等。

## 使用方法

### 先决条件
- Windows 系统（本仓库在 Windows 环境测试），并提供 FreeCAD 安装路径（例如 `D:\Apps\FreeCAD`）。
- Python 环境：推荐创建虚拟环境并安装 `trimesh`、`matplotlib`（见 `requirements.txt`），但脚本对缺失依赖有回退策略（用 `matplotlib` 渲染或直接拷贝样本自带 `screenshot.png`）。

### 命令示例（单个样本）
```powershell
python .\benchmark\render_views.py .\benchmark\resources\tmp_sample\abc\00000002\cad.step --freecad-cmd D:\Apps\FreeCAD\bin\FreeCADCmd.exe
```
输出会写入 `..\00000002\cad_front.png` 等六张图片。

### 命令示例（批量模式, 待脚本支持）
```powershell
python .\benchmark\render_views.py --batch --batch-root .\benchmark\resources --freecad-cmd D:\Apps\FreeCAD\bin\FreeCADCmd.exe
```
该命令会递归查找 `batch-root` 下的所有 `*/cad.step` 并为每个 sample 生成 6 张视图。

## 参数说明
- `step`：对单个 STEP 文件进行渲染（互斥于 `--batch`）。
- `--batch`：启用批量模式，使用 `--batch-root` 指定根目录。
- `--batch-root`：批量模式时的起点目录（默认 `benchmark/resources`）。
- `--freecad-cmd`：FreeCADCmd 可执行文件路径（默认 `D:\Apps\FreeCAD\bin\FreeCADCmd.exe`）。
- `--overwrite`：若输出已存在，是否覆盖（可选开关）。

## 故障排查
- FreeCAD 无法生成 STL：
  - 检查 `FreeCADCmd.exe` 路径是否正确；可手动在 PowerShell 中执行 `D:\Apps\FreeCAD\bin\FreeCADCmd.exe your_script.py your.step out.stl` 来调试。
  - 某些 STEP 具有特殊的拓扑或扩展，FreeCAD 的 Import 模块可能无法解析（日志会输出错误），这时可在 FreeCAD GUI 中打开 STEP 并导出 STL 作为替代。

- `trimesh` 的 `save_image` 报错（例如 `requires pip install "pyglet<2"`）
  - 可以 `pip install "pyglet<2"` 或使用 conda 安装对应包以启用窗口化渲染；否则脚本会用 `matplotlib` 作为回退方案。

- `matplotlib` 渲染效果差：
  - 这是设计使然（快速可用）。若需要一致性或高质量渲染，请使用 Blender/FreeCAD 渲染器或启用 `trimesh` 的窗口化/离屏渲染。

## 建议改进
- 使用 Blender 的 Python API 做离线渲染以获得更好的光照/材质控制。
- 使用 `trimesh` + `pyrender` + OSMesa 做真正的离屏渲染（更接近真实效果，且可在无 GUI 的服务器上运行）。

