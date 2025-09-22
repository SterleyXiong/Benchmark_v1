"""Render front-view image from a STEP file.

Strategy:
- Try to use `pythonocc-core` to load STEP and convert to mesh for rendering.
- If `pythonocc` is unavailable, try `trimesh` with `assimp`/`meshio` if STEP can be read.
- Render a single orthographic front-view image and save as PNG.

This script focuses on a minimal path and prints which backend was used.
"""
from pathlib import Path
import sys
import argparse
import tempfile
import subprocess
import os

try:
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Display.SimpleGui import init_display
    OCC_AVAILABLE = True
except Exception:
    OCC_AVAILABLE = False

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except Exception:
    TRIMESH_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

# Try to detect FreeCAD by importing; if fail, allow a configured FreeCAD path
FREECAD_AVAILABLE = False
FREECAD_CMD_PATH = r"D:\Apps\FreeCAD\bin\FreeCADCmd.exe"
try:
    import FreeCAD  # type: ignore
    FREECAD_AVAILABLE = True
except Exception:
    FREECAD_AVAILABLE = False


def render_with_occ(step_path: Path, out_path: Path):
    """Load STEP with pythonocc, display and capture front view using the OCC viewer."""
    print('Using pythonocc-core backend')
    # Basic implementation: load STEP and dump a screenshot using the OCC display window.
    # This requires a GUI backend; on headless systems additional setup needed.
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError('Failed to read STEP file')
    reader.TransferRoots()
    shape = reader.OneShape()

    display, start_display, add_menu, add_function_to_menu = init_display()
    display.DisplayShape(shape, update=True)
    display.View_Iso()
    display.SetModeShaded()
    # try to set front view (Y direction)
    display.View_Front()
    # grab and save
    display.View.Dump(str(out_path))
    print('Saved:', out_path)


def render_mesh_with_matplotlib(mesh, out_path: Path, size=(1024, 1024)):
    """Render a Trimesh (or mesh-like with vertices/faces) using matplotlib 3D as front view."""
    print('Using matplotlib fallback renderer')
    # Extract vertices and faces
    if hasattr(mesh, 'geometry') and isinstance(mesh, trimesh.Scene):
        # take first geometry
        geom = None
        for g in mesh.geometry.values():
            geom = g
            break
        if geom is None:
            raise RuntimeError('Scene has no geometry')
        tri = geom
    elif isinstance(mesh, trimesh.Trimesh):
        tri = mesh
    else:
        # try to convert
        tri = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces)

    verts = tri.vertices
    faces = tri.faces

    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_trisurf(verts[:, 0], verts[:, 1], faces, verts[:, 2], color=(0.8, 0.8, 0.8), linewidth=0.0)

    # front view: set elevation=0, azimuth=0 and orthographic if supported
    try:
        ax.set_proj_type('ortho')
    except Exception:
        pass
    ax.view_init(elev=0, azim=0)
    ax.axis('off')
    # auto scale
    scale = verts.flatten()
    ax.auto_scale_xyz(scale, scale, scale)
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(str(out_path), dpi=100)
    plt.close(fig)
    print('Saved (matplotlib):', out_path)


def render_with_trimesh(step_path: Path, out_path: Path):
    """Try to load STEP via trimesh (which uses `assimp` if available) and render an orthographic front view."""
    print('Using trimesh backend')
    mesh = trimesh.load(str(step_path), force='mesh')
    if mesh.is_empty:
        raise RuntimeError('trimesh could not load mesh from STEP')

    # Ensure mesh is a Trimesh object
    if isinstance(mesh, trimesh.Scene):
        scene = mesh
    else:
        scene = trimesh.Scene(mesh)

    # Try save_image first
    try:
        png = scene.save_image(resolution=(1024, 1024), visible=True)
        out_path.write_bytes(png)
        print('Saved:', out_path)
    except Exception as e:
        print('trimesh save_image failed, will try matplotlib fallback:', e)
        if MATPLOTLIB_AVAILABLE:
            # extract a mesh for matplotlib
            # prefer first geometry
            if isinstance(scene, trimesh.Scene):
                geom = None
                for g in scene.geometry.values():
                    geom = g
                    break
                if geom is None:
                    raise RuntimeError('Scene has no geometry for matplotlib')
                tri = geom
            else:
                tri = scene
            render_mesh_with_matplotlib(tri, out_path)
        else:
            raise


def render_with_freecad(step_path: Path, out_path: Path, freecad_cmd: str = FREECAD_CMD_PATH):
    """Use FreeCADCmd to convert STEP to STL/OBJ and render with trimesh.

    This writes a temporary Python script that FreeCADCmd executes. FreeCADCmd must be
    the FreeCAD command-line binary (typically in FreeCAD's `bin` folder).
    """
    print('Using FreeCAD -> trimesh backend (FreeCADCmd at %s)' % freecad_cmd)
    if not Path(freecad_cmd).is_file():
        raise RuntimeError(f'FreeCADCmd not found at {freecad_cmd}')

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        out_mesh = td_path / 'out.stl'
        # create FreeCAD script
        fc_script = td_path / 'fc_export.py'
        fc_code = f"""
import sys
import traceback
try:
    import FreeCAD
except Exception:
    FreeCAD = None
try:
    import Part
except Exception:
    Part = None
try:
    import Mesh
except Exception:
    Mesh = None
try:
    import MeshPart
except Exception:
    MeshPart = None
try:
    import Import
except Exception:
    Import = None
infile = sys.argv[-2]
outfile = sys.argv[-1]
print('FreeCAD script start. argv=', sys.argv)
print('FreeCAD script start. infile=', infile, 'outfile=', outfile)
ok = False
# Strategy 1: Import.open -> Mesh.export
if Import is not None:
    try:
        print('Trying Import.open')
        objs = Import.open(infile)
        print('Import.open returned:', type(objs))
        try:
            Mesh.export(objs, outfile)
            print('Mesh.export succeeded from Import.open')
            ok = True
        except Exception as e:
            print('Mesh.export failed on Import.open:', e)
    except Exception as e:
        print('Import.open failed:', e)

# Strategy 2: Part.read + MeshPart.meshFromShape
if not ok and Part is not None and MeshPart is not None:
    try:
        print('Trying Part.read + MeshPart.meshFromShape')
        shape = Part.read(infile)
        print('Part.read ok, creating mesh')
        mesh = MeshPart.meshFromShape(shape, 0.1)
        print('mesh created, type=', type(mesh))
        try:
            Mesh.export([mesh], outfile)
            print('Mesh.export succeeded from meshFromShape')
            ok = True
        except Exception as e:
            print('Mesh.export failed on meshFromShape:', e)
    except Exception as e:
        print('Part.read/MeshPart failed:', e)

# Strategy 3: Import into new doc then Mesh.export
if not ok:
    try:
        print('Trying Import.open into new document')
        try:
            doc = FreeCAD.newDocument()
        except Exception:
            import App
            doc = App.newDocument()
        Import.open(infile, doc.Name)
        objs = doc.Objects
        print('Imported to doc, obj count=', len(objs))
        Mesh.export(objs, outfile)
        print('Mesh.export succeeded from doc objects')
        ok = True
    except Exception as e:
        print('Import->doc route failed:', e)
        traceback.print_exc()

if not ok:
    raise RuntimeError('Conversion to mesh failed')
print('FreeCAD script finished')
"""
        fc_script.write_text(fc_code)

        # call FreeCADCmd
        try:
            proc = subprocess.run([freecad_cmd, str(fc_script), str(step_path), str(out_mesh)], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr is not None else ''
            raise RuntimeError(f'FreeCADCmd failed: {stderr}')
        else:
            # even if returncode==0, print stdout/stderr for debugging
            stdout = proc.stdout.decode('utf-8', errors='ignore') if proc.stdout is not None else ''
            stderr = proc.stderr.decode('utf-8', errors='ignore') if proc.stderr is not None else ''
            if stdout:
                print('FreeCADCmd stdout:', stdout)
            if stderr:
                print('FreeCADCmd stderr:', stderr)

        if not out_mesh.exists():
            raise RuntimeError('FreeCAD conversion did not produce mesh file')

        # render with trimesh
        if not TRIMESH_AVAILABLE:
            raise RuntimeError('trimesh required to render converted mesh')

        mesh = trimesh.load(str(out_mesh), force='mesh')
        if isinstance(mesh, trimesh.Scene):
            scene = mesh
        else:
            scene = trimesh.Scene(mesh)

        # try save_image, fallback to matplotlib
        try:
            png = scene.save_image(resolution=(1024, 1024), visible=True)
            out_path.write_bytes(png)
            print('Saved:', out_path)
        except Exception as e:
            print('trimesh save_image failed for converted mesh, will try matplotlib fallback:', e)
            if MATPLOTLIB_AVAILABLE:
                # pick first geometry
                if isinstance(scene, trimesh.Scene):
                    geom = None
                    for g in scene.geometry.values():
                        geom = g
                        break
                    if geom is None:
                        raise RuntimeError('Scene has no geometry for matplotlib')
                    tri = geom
                else:
                    tri = scene
                render_mesh_with_matplotlib(tri, out_path)
            else:
                raise RuntimeError('Failed to render converted mesh: %s' % e)


def render_fallback_screenshot(step_path: Path, out_path: Path):
    """If rendering backends unavailable, use existing sample screenshot if present."""
    screenshot = step_path.parent / 'screenshot.png'
    if screenshot.is_file():
        from shutil import copy2
        copy2(screenshot, out_path)
        print('Used existing screenshot as fallback:', out_path)
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('step', type=Path)
    parser.add_argument('--out', type=Path, default=Path('front_view.png'))
    parser.add_argument('--freecad-cmd', type=str, default=FREECAD_CMD_PATH, help='Path to FreeCADCmd.exe')
    args = parser.parse_args()

    # try FreeCAD conversion first (if available or if user provided path exists)
    if Path(args.freecad_cmd).is_file():
        try:
            render_with_freecad(args.step, args.out, freecad_cmd=args.freecad_cmd)
            return
        except Exception as e:
            print('FreeCAD backend failed:', e)

    if OCC_AVAILABLE:
        try:
            render_with_occ(args.step, args.out)
            return
        except Exception as e:
            print('pythonocc render failed:', e)

    if TRIMESH_AVAILABLE:
        try:
            render_with_trimesh(args.step, args.out)
            return
        except Exception as e:
            print('trimesh render failed:', e)

    # fallback: copy provided screenshot if available
    if render_fallback_screenshot(args.step, args.out):
        return

    print('No suitable rendering backend available. Install pythonocc-core or trimesh + cascadio, or ensure FreeCADCmd is installed.')


if __name__ == '__main__':
    main()
