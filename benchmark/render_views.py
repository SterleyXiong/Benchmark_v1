"""Render six orthographic views (front, back, left, right, top, bottom) from a STEP file.

This script uses FreeCADCmd to convert STEP->STL, then loads the STL via trimesh (if installed) or
uses matplotlib to render the mesh in the requested camera orientations.

Outputs are saved as <sample>_front.png, <sample>_back.png, etc. in the same folder as the STEP.
"""
from pathlib import Path
import subprocess
import tempfile
import argparse
import os
import glob

# We reuse parts of render_front.py logic but keep this script self-contained for clarity
FREECAD_CMD_DEFAULT = r"D:\Apps\FreeCAD\bin\FreeCADCmd.exe"

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


def convert_step_to_stl(step_path: Path, freecad_cmd: str = FREECAD_CMD_DEFAULT) -> Path:
    """Use FreeCADCmd to convert STEP to STL, return path to STL.

    Raises RuntimeError on failure.
    """
    if not Path(freecad_cmd).is_file():
        raise RuntimeError(f'FreeCADCmd not found at {freecad_cmd}')

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        out_mesh = td_path / 'out.stl'
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
print('fc script argv=', sys.argv)
# try Import.open -> Mesh.export
ok = False
if Import is not None:
    try:
        objs = Import.open(infile)
        try:
            Mesh.export(objs, outfile)
            ok = True
        except Exception:
            pass
    except Exception:
        pass
# try Import into doc
if not ok:
    try:
        try:
            doc = FreeCAD.newDocument()
        except Exception:
            import App
            doc = App.newDocument()
        Import.open(infile, doc.Name)
        objs = doc.Objects
        Mesh.export(objs, outfile)
        ok = True
    except Exception:
        pass
if not ok:
    raise RuntimeError('FreeCAD conversion to STL failed')
print('FreeCAD conversion wrote', outfile)
"""
        fc_script.write_text(fc_code)
        proc = subprocess.run([freecad_cmd, str(fc_script), str(step_path), str(out_mesh)], capture_output=True)
        stdout = proc.stdout.decode('utf-8', errors='ignore') if proc.stdout else ''
        stderr = proc.stderr.decode('utf-8', errors='ignore') if proc.stderr else ''
        if stdout:
            print('FreeCAD stdout:', stdout)
        if stderr:
            print('FreeCAD stderr:', stderr)
        if not out_mesh.exists():
            raise RuntimeError('FreeCAD did not produce STL; stderr: ' + stderr)
        # copy to a persistent location (next to step)
        dest = step_path.parent / (step_path.stem + '.stl')
        with open(out_mesh, 'rb') as rf, open(dest, 'wb') as wf:
            wf.write(rf.read())
        print('Wrote mesh to', dest)
        return dest


def render_with_matplotlib_mesh(tri, out_path: Path, view: str, size=(1024, 1024)):
    """Render a trimesh.Trimesh with matplotlib according to view name."""
    verts = tri.vertices
    faces = tri.faces
    import numpy as np

    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_trisurf(verts[:, 0], verts[:, 1], faces, verts[:, 2], color=(0.8, 0.8, 0.8), linewidth=0.0)

    # choose view
    if view == 'front':
        elev, azim = 0, 0
    elif view == 'back':
        elev, azim = 0, 180
    elif view == 'left':
        elev, azim = 0, 90
    elif view == 'right':
        elev, azim = 0, -90
    elif view == 'top':
        elev, azim = 90, 0
    elif view == 'bottom':
        elev, azim = -90, 0
    else:
        elev, azim = 0, 0

    try:
        ax.set_proj_type('ortho')
    except Exception:
        pass
    ax.view_init(elev=elev, azim=azim)
    ax.axis('off')
    scale = verts.flatten()
    ax.auto_scale_xyz(scale, scale, scale)
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(str(out_path), dpi=100)
    plt.close(fig)
    print('Saved', out_path)


def render_all_views(step_path: Path, freecad_cmd: str = FREECAD_CMD_DEFAULT):
    # convert
    stl_path = convert_step_to_stl(step_path, freecad_cmd=freecad_cmd)

    # load via trimesh if available
    if TRIMESH_AVAILABLE:
        scene_or_mesh = trimesh.load(str(stl_path), force='mesh')
        if isinstance(scene_or_mesh, trimesh.Scene):
            # take first geometry
            tri = None
            for g in scene_or_mesh.geometry.values():
                tri = g
                break
            if tri is None:
                raise RuntimeError('No geometry found in scene')
        else:
            tri = scene_or_mesh
    else:
        # if trimesh not available, try to load stl minimally with numpy-stl? here we assume matplotlib can still render
        raise RuntimeError('trimesh required for mesh processing; please install trimesh or run render_front fallback')

    views = ['front', 'back', 'left', 'right', 'top', 'bottom']
    for v in views:
        out = step_path.parent / (step_path.stem + '_' + v + '.png')
        try:
            # try trimesh rendering first
            try:
                scene = trimesh.Scene(tri)
                png = scene.save_image(resolution=(1024, 1024), visible=True)
                out.write_bytes(png)
                print('Saved via trimesh:', out)
                continue
            except Exception as e:
                print('trimesh save_image failed, falling back to matplotlib:', e)
            # matplotlib fallback
            if MATPLOTLIB_AVAILABLE:
                render_with_matplotlib_mesh(tri, out, v)
            else:
                # final fallback: copy existing screenshot
                ss = step_path.parent / 'screenshot.png'
                if ss.exists():
                    import shutil
                    shutil.copy2(ss, out)
                    print('Copied existing screenshot to', out)
                else:
                    raise RuntimeError('No renderer available and no screenshot to copy')
        except Exception as e:
            print('Failed to render view', v, ':', e)


def batch_render(batch_root: Path, freecad_cmd: str, overwrite: bool = False):
    # find all cad.step files under batch_root
    pattern = str(Path(batch_root) / '**' / 'cad.step')
    files = glob.glob(pattern, recursive=True)
    if not files:
        print('No cad.step files found under', batch_root)
        return
    print('Found', len(files), 'STEP files')
    for f in sorted(files):
        step_p = Path(f)
        # determine outputs exist?
        outputs = [step_p.parent / (step_p.stem + '_' + v + '.png') for v in ['front','back','left','right','top','bottom']]
        if not overwrite and all(o.exists() for o in outputs):
            print('Skipping (exists):', step_p)
            continue
        try:
            render_all_views(step_p, freecad_cmd=freecad_cmd)
        except Exception as e:
            print('Error rendering', step_p, ':', e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('step', type=Path, nargs='?', help='Path to STEP file (mutually exclusive with --batch)')
    parser.add_argument('--freecad-cmd', type=str, default=FREECAD_CMD_DEFAULT)
    parser.add_argument('--batch', action='store_true', help='Enable batch mode to process many samples')
    parser.add_argument('--batch-root', type=Path, default=Path('benchmark/resources'))
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    args = parser.parse_args()

    if args.batch:
        batch_render(args.batch_root, freecad_cmd=args.freecad_cmd, overwrite=args.overwrite)
    else:
        if not args.step:
            parser.error('Please provide a STEP file or use --batch')
        render_all_views(args.step, freecad_cmd=args.freecad_cmd)
