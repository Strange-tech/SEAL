#!/usr/bin/env python3
"""room_viewer.py — serve a web viewer for room.obj.

Renders the OBB boxes written by ``export_obj`` / the auto-materialize step in a
browser (Three.js, loaded from a CDN). Hovering a box shows its OBB local XYZ
axes (X red, Y green, Z blue) and its id; moving the pointer away hides them.

The OBJ vertex order is the one produced by ``sdk.geometry.obb_corners`` (see
``sdk.scene.obbs_to_obj``), so for each object the three edges from corner 0 are
exactly the local +x/+y/+z axes in the y-up room frame — no re-derivation needed.

Usage:
    python room_viewer.py [--obj room.obj] [--host 0.0.0.0] [--port 8000]

Dependencies: Python 3 stdlib only (the browser fetches Three.js from jsDelivr).
"""

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _norm(v):
    n = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    return [x / n for x in v] if n > 1e-12 else [0.0, 0.0, 0.0]


def _len(v):
    return (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5


def parse_obj(path):
    """Parse room.obj into a list of OBB metadata dicts.

    Each entry: ``{"id", "type", "center": [x,y,z], "dims": [w,h,l],
    "axes": {"x": [...], "y": [...], "z": [...]}}``. The axes are unit vectors in
    the y-up room frame (the OBB local x/y/z directions).
    """
    objs = []
    cur_id = None
    cur_type = None
    verts = []

    def flush():
        nonlocal cur_id, cur_type, verts
        if cur_id is not None and len(verts) == 8:
            center = [sum(v[i] for v in verts) / 8.0 for i in range(3)]
            x_axis = _norm(_sub(verts[1], verts[0]))   # corner 0 -> 1 = +x
            y_axis = _norm(_sub(verts[3], verts[0]))   # corner 0 -> 3 = +y
            z_axis = _norm(_sub(verts[4], verts[0]))   # corner 0 -> 4 = +z
            dims = [
                _len(_sub(verts[1], verts[0])),
                _len(_sub(verts[3], verts[0])),
                _len(_sub(verts[4], verts[0])),
            ]
            objs.append({
                "id": cur_id,
                "type": cur_type or "object",
                "center": center,
                "dims": dims,
                "axes": {"x": x_axis, "y": y_axis, "z": z_axis},
            })
        verts = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("o "):
                flush()
                cur_id = s[2:].strip()
                cur_type = None
            elif s.startswith("g "):
                cur_type = s[2:].strip()
            elif s.startswith("v "):
                parts = s.split()
                if len(parts) >= 4:
                    verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            # faces are ignored; only the 8 vertices per object are needed
    flush()
    return objs


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>room.obj viewer</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #0e0e14; }
  #viewer { position: fixed; inset: 0; }
  #tooltip { position: fixed; pointer-events: none; display: none; background: rgba(18,18,28,0.92); color: #eaeaea;
             padding: 7px 11px; border-radius: 6px; font-size: 13px; border: 1px solid #3a3a4a; z-index: 10; white-space: nowrap; }
  #tooltip .id { font-weight: 700; color: #ffd166; }
  #tooltip .dim { color: #9aa; font-size: 12px; }
  #legend { position: fixed; bottom: 12px; left: 12px; background: rgba(18,18,28,0.85); color: #bbb;
            padding: 8px 12px; border-radius: 6px; font-size: 12px; z-index: 10; line-height: 1.5; }
  #legend .x { color: #ff4444; } #legend .y { color: #44ff44; } #legend .z { color: #4488ff; }
  #err { position: fixed; inset: 0; display: none; align-items: center; justify-content: center; color: #ff7777;
         font-size: 15px; z-index: 20; text-align: center; padding: 24px; }
</style>
</head>
<body>
<div id="viewer"></div>
<div id="tooltip"></div>
<div id="legend">OBB axes: <span class="x">X</span> &nbsp;<span class="y">Y</span>&nbsp;(up)&nbsp; <span class="z">Z</span> &nbsp;&middot;&nbsp; hover a box to show its axes + id</div>
<div id="err"></div>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
(function () {
  var err = document.getElementById('err');
  function fail(msg) { err.textContent = msg; err.style.display = 'flex'; }
  if (typeof THREE === 'undefined') { fail('Failed to load Three.js from CDN. Check network access to cdn.jsdelivr.net.'); return; }

  var container = document.getElementById('viewer');
  var tooltip = document.getElementById('tooltip');

  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0x14141e);

  var camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.01, 1000);
  var renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  var d1 = new THREE.DirectionalLight(0xffffff, 0.85); d1.position.set(6, 10, 8); scene.add(d1);
  var d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-6, -4, -8); scene.add(d2);

  var controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  var TYPE_COLORS = { wall: 0x8899aa, floor: 0x559966, door: 0xaa7744, window: 0x6699cc, object: 0xcc9966 };

  var group = new THREE.Group();
  scene.add(group);
  var meshes = [];

  var axesGroup = new THREE.Group();
  scene.add(axesGroup);
  var hovered = null;

  function clearAxes() { while (axesGroup.children.length) axesGroup.remove(axesGroup.children[0]); }
  function showAxes(o) {
    clearAxes();
    var c = new THREE.Vector3(o.center[0], o.center[1], o.center[2]);
    var m = Math.max(o.dims[0], o.dims[1], o.dims[2]);
    var len = Math.max(m * 0.6, 0.15);
    var ax = new THREE.Vector3(o.axes.x[0], o.axes.x[1], o.axes.x[2]);
    var ay = new THREE.Vector3(o.axes.y[0], o.axes.y[1], o.axes.y[2]);
    var az = new THREE.Vector3(o.axes.z[0], o.axes.z[1], o.axes.z[2]);
    axesGroup.add(new THREE.ArrowHelper(ax, c, len, 0xff4444, len * 0.25, len * 0.12));
    axesGroup.add(new THREE.ArrowHelper(ay, c, len, 0x44ff44, len * 0.25, len * 0.12));
    axesGroup.add(new THREE.ArrowHelper(az, c, len, 0x4488ff, len * 0.25, len * 0.12));
  }

  function setHover(mesh) {
    if (hovered === mesh) return;
    if (hovered) { hovered.material.emissive.setHex(0x000000); hovered.material.opacity = hovered.userData.baseOpacity; }
    hovered = mesh;
    if (mesh) { mesh.material.emissive.setHex(0x553300); mesh.material.opacity = 0.12; }
  }

  function build(objs) {
    objs.forEach(function (o) {
      var w = Math.max(o.dims[0], 1e-3), h = Math.max(o.dims[1], 1e-3), l = Math.max(o.dims[2], 1e-3);
      var geo = new THREE.BoxGeometry(w, h, l);
      var color = TYPE_COLORS[o.type] || 0xcc9966;
      var mat = new THREE.MeshStandardMaterial({
        color: color, roughness: 0.6, metalness: 0.05,
        transparent: true, opacity: 0.55, depthWrite: false
      });
      var mesh = new THREE.Mesh(geo, mat);
      var rot = new THREE.Matrix4();
      rot.set(
        o.axes.x[0], o.axes.y[0], o.axes.z[0], 0,
        o.axes.x[1], o.axes.y[1], o.axes.z[1], 0,
        o.axes.x[2], o.axes.y[2], o.axes.z[2], 0,
        0, 0, 0, 1
      );
      mesh.quaternion.setFromRotationMatrix(rot);
      mesh.position.set(o.center[0], o.center[1], o.center[2]);
      mesh.userData = { o: o, baseOpacity: 0.55 };
      group.add(mesh);
      meshes.push(mesh);
    });

    if (!meshes.length) { fail('No OBBs found. Run the layout first to generate room.obj.'); return; }

    var box = new THREE.Box3().setFromObject(group);
    var center = box.getCenter(new THREE.Vector3());
    var size = box.getSize(new THREE.Vector3());
    var maxDim = Math.max(size.x, size.y, size.z) || 1;
    var dist = maxDim * 1.7;
    camera.position.set(center.x + dist * 0.4, center.y + dist * 0.35, center.z + dist);
    camera.near = Math.max(0.001, maxDim / 1000);
    camera.far = maxDim * 60 + 100;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  fetch('/meta.json').then(function (r) { return r.json(); }).then(function (data) {
    if (data && data.error) { fail('Server error: ' + data.error); return; }
    build(Array.isArray(data) ? data : []);
  }).catch(function (e) {
    fail('Failed to load /meta.json: ' + e);
  });

  var raycaster = new THREE.Raycaster();
  var pointer = new THREE.Vector2();
  window.addEventListener('mousemove', function (ev) {
    pointer.x = (ev.clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(ev.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    var hits = raycaster.intersectObjects(meshes, false);
    if (hits.length) {
      var mesh = hits[0].object;
      var o = mesh.userData.o;
      setHover(mesh);
      showAxes(o);
      tooltip.innerHTML = '<span class="id">' + o.id + '</span>'
        + '<br>type: ' + o.type
        + '<br><span class="dim">' + o.dims.map(function (d) { return d.toFixed(3); }).join(' x ') + ' m</span>';
      tooltip.style.display = 'block';
      tooltip.style.left = (ev.clientX + 14) + 'px';
      tooltip.style.top = (ev.clientY + 14) + 'px';
    } else {
      setHover(null);
      clearAxes();
      tooltip.style.display = 'none';
    }
  });

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  window.addEventListener('resize', function () {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  });
})();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    obj_path = None

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
        elif path == "/meta.json":
            try:
                objs = parse_obj(self.obj_path)
            except Exception as e:
                self._send(500, "application/json", json.dumps({"error": str(e)}).encode("utf-8"))
                return
            self._send(200, "application/json", json.dumps(objs).encode("utf-8"))
        elif path == "/room.obj":
            try:
                with open(self.obj_path, "rb") as f:
                    data = f.read()
            except OSError as e:
                self._send(404, "text/plain", str(e).encode("utf-8"))
                return
            self._send(200, "text/plain", data)
        else:
            self._send(404, "text/plain", b"not found")

    def log_message(self, fmt, *args):
        pass  # quiet


def main():
    ap = argparse.ArgumentParser(description="Serve a web viewer for room.obj")
    ap.add_argument("--obj", default="room.obj", help="Path to the OBJ file (default: room.obj)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = ap.parse_args()

    obj_path = os.path.abspath(args.obj)
    if not os.path.isfile(obj_path):
        print(f"warning: OBJ not found yet: {obj_path} (viewer will show nothing until room.obj exists)",
              file=sys.stderr)
    Handler.obj_path = obj_path

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"room_viewer serving {obj_path}")
    print(f"Open http://{args.host}:{args.port}/ in a browser")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)


if __name__ == "__main__":
    main()
