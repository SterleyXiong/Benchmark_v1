渲染说明

脚本 `render_front.py` 尝试加载 STEP 文件并渲染单张前视图。使用方法：

1. 建议创建虚拟环境（Windows PowerShell）:

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 运行脚本：

```
python render_front.py resources/tmp_sample/abc/00000002/cad.step --out out_front.png
```

实现说明：
- 优先使用 `pythonocc-core`（需要 OpenCASCADE 环境，会打开一个视窗并截图）。
- 如果没有 `pythonocc-core`，脚本会尝试使用 `trimesh`（依赖 `assimp` 通过系统安装或 `pyassimp`）。

注意事项：
- 在无头服务器上使用 `pythonocc` 可能需要额外的环境配置或 xvfb；Windows 上请确保有可用的 GUI。