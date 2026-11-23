#!/usr/bin/env python3
"""room_viewer.py — serve a Three.js viewer for SEAL outputs.

Renders two things in one browser scene:

* **layout** — a LayoutAgent scene-graph JSON (``nodes``/``edges``) from
  ``BaseAgent/output/layoutagent/``. Each node is drawn as a semi-transparent OBB
  box; hovering it shows its local XYZ axes (X red / Y green / Z blue) and id.
* **arti** — an ArtiAgent result JSON (``asset_dir`` + ``real_bbox``) from
  ``BaseAgent/output/artiagent/``. The viewer resolves the record's materialized
  ``model.urdf`` + ``assets/meshes/*.obj`` and renders the articulated object,
  with a toggle to animate each joint across its ``<limit lower/upper>`` range.

A JSON config selects which files to show:

    python room_viewer.py --config scene.json

where ``scene.json`` is::

    {"layout": "output/layoutagent/kitchen.json",
     "arti":   "output/artiagent/cabinet.json"}

``arti`` may also be a list to render several articulated objects together::

    {"layout": "output/layoutagent/kitchen.json",
     "arti":   ["output/artiagent/cabinet.json", "output/artiagent/drawer.json"]}

Paths are resolved against the BaseAgent directory (or the config file's
directory, or ``output/``) and may be absolute. You can also pass ``--layout`` /
``--arti`` directly, and if neither is given the most recently written file from
each agent is auto-discovered.

The ``--config`` file is re-read on every page load, so edit it and refresh the
browser to hot-reload the scene without restarting the server.

Frames / conventions: the layout JSON uses ``C``(center)/``D``(dims)/``theta``
(degrees, R = Rx @ Ry @ Rz, y-up); the URDF uses ``xyz``/``rpy``(radians) and
standard joint ``origin``/``axis``/``limit``. Dependencies: Python 3 stdlib only;
the browser fetches Three.js + OrbitControls + OBJLoader from jsDelivr.
"""

import argparse
import json
import math
import os
import sys
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_ROOT = Path(__file__).resolve().parent          # BaseAgent directory
OUTPUT_DIR = BASE_ROOT / "output"
ARTI_DIR = Path(os.environ.get("ARTI_AGENT_DIR", str(BASE_ROOT.parent / "ArtiAgent")))
ASSET_JSON_DIR = BASE_ROOT / "assets" / "10_assets_only_text"


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def _vec3(s, default=(0.0, 0.0, 0.0)):
    if not s:
        return list(default)
    return [float(x) for x in s.split()]


def _rgba(s):
    p = s.split()
    if len(p) < 3:
        return [0.8, 0.8, 0.8, 1.0]
    return [float(p[0]), float(p[1]), float(p[2]), float(p[3]) if len(p) > 3 else 1.0]


def _elem_attr(elem, tag, attr):
    e = elem.find(tag)
    return e.get(attr) if e is not None else None


def load_layout_scene(path):
    """Read a LayoutAgent scene-graph JSON into ``{nodes, edges}`` (OBB form)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = []
    for n in data.get("nodes", []):
        nodes.append({
            "id": n.get("id", ""),
            "type": n.get("type", "object"),
            "center": [float(v) for v in n.get("C", (0.0, 0.0, 0.0))],
            "dims": [float(v) for v in n.get("D", (1.0, 1.0, 1.0))],
            "theta": [float(v) for v in n.get("theta", (0.0, 0.0, 0.0))],  # deg, R=Rx@Ry@Rz
        })
    return {"nodes": nodes, "edges": data.get("edges", [])}


def parse_urdf(path):
    """Parse a URDF into a flat, frontend-friendly structure.

    Returns ``{name, links, joints, roots, meshes}`` where ``links`` is a dict
    name -> ``{name, visuals:[{mesh_key, origin:{xyz,rpy}, color}]}``, ``joints``
    is a list of ``{name, type, parent, child, origin, axis, lower, upper}``,
    ``roots`` lists the links that no joint treats as a child, and ``meshes`` is
    ``[{key, file}]`` (deduplicated relative mesh filenames).
    """
    tree = ET.parse(path)
    robot = tree.getroot()

    materials = {}
    for m in robot.findall("material"):
        name = m.get("name")
        c = m.find("color")
        if name and c is not None:
            materials[name] = _rgba(c.get("rgba"))

    links = {}
    for link in robot.findall("link"):
        name = link.get("name")
        visuals = []
        for v in link.findall("visual"):
            geom = v.find("geometry")
            if geom is None:
                continue
            origin = v.find("origin")
            xyz = _vec3(origin.get("xyz")) if origin is not None else [0.0, 0.0, 0.0]
            rpy = _vec3(origin.get("rpy")) if origin is not None else [0.0, 0.0, 0.0]
            color = None
            mat = v.find("material")
            if mat is not None:
                mn = mat.get("name")
                if mn and mn in materials:
                    color = materials[mn]
                c = mat.find("color")
                if c is not None:
                    color = _rgba(c.get("rgba"))
            vis = {"origin": {"xyz": xyz, "rpy": rpy}, "color": color}
            mesh = geom.find("mesh")
            if mesh is not None and mesh.get("filename"):
                vis["mesh"] = mesh.get("filename")
                vis["scale"] = _vec3(mesh.get("scale"), (1.0, 1.0, 1.0))
                visuals.append(vis)
                continue
            box = geom.find("box")
            if box is not None and box.get("size"):
                vis["primitive"] = {"type": "box", "size": _vec3(box.get("size"))}
                visuals.append(vis)
                continue
            cyl = geom.find("cylinder")
            if cyl is not None:
                vis["primitive"] = {
                    "type": "cylinder",
                    "radius": float(cyl.get("radius", 0.5)),
                    "length": float(cyl.get("length", 1.0)),
                }
                visuals.append(vis)
                continue
            sph = geom.find("sphere")
            if sph is not None:
                vis["primitive"] = {"type": "sphere", "radius": float(sph.get("radius", 0.5))}
                visuals.append(vis)
        links[name] = {"name": name, "visuals": visuals}

    joints = []
    for j in robot.findall("joint"):
        origin = j.find("origin")
        xyz = _vec3(origin.get("xyz")) if origin is not None else [0.0, 0.0, 0.0]
        rpy = _vec3(origin.get("rpy")) if origin is not None else [0.0, 0.0, 0.0]
        axis = j.find("axis")
        ax = _vec3(axis.get("xyz")) if axis is not None else [1.0, 0.0, 0.0]
        jtype = j.get("type", "fixed")
        limit = j.find("limit")
        lower = float(limit.get("lower", 0.0)) if limit is not None else 0.0
        upper = float(limit.get("upper", 0.0)) if limit is not None else 0.0
        if jtype == "continuous":
            # continuous joints carry no <limit lower/upper>; give them a full-turn
            # sweep so the animation actually spins wheels / cranks / pedals.
            lower, upper = 0.0, 2.0 * math.pi
        joints.append({
            "name": j.get("name"),
            "type": jtype,
            "parent": _elem_attr(j, "parent", "link"),
            "child": _elem_attr(j, "child", "link"),
            "origin": {"xyz": xyz, "rpy": rpy},
            "axis": ax,
            "lower": lower,
            "upper": upper,
        })

    children = {j["child"] for j in joints if j["child"]}
    roots = [n for n in links if n not in children]

    # dedupe mesh files -> stable keys
    mesh_files = []
    mesh_keys = {}

    def key_for(filename):
        if filename not in mesh_keys:
            mesh_keys[filename] = "m%d" % len(mesh_files)
            mesh_files.append(filename)
        return mesh_keys[filename]

    for ln in links.values():
        for vis in ln["visuals"]:
            if "mesh" in vis:
                vis["mesh_key"] = key_for(vis.pop("mesh"))

    return {
        "name": robot.get("name", "robot"),
        "links": links,
        "joints": joints,
        "roots": roots,
        "meshes": [{"key": "m%d" % i, "file": f} for i, f in enumerate(mesh_files)],
    }


def resolve_urdf(asset_dir):
    """Locate ``model.urdf`` for an ArtiAgent ``asset_dir`` (record dir or materialization dir)."""
    if not asset_dir:
        return None
    ad = Path(asset_dir)
    if not ad.is_absolute():
        ad = BASE_ROOT / ad
    cand = ad / "model.urdf"
    if cand.is_file():
        return cand.resolve()
    # `asset_dir` is the record dir (data/records/<id>/); the materialized URDF lives in
    # the sibling materialization dir keyed by the same record id.
    record_id = ad.name
    mat = ARTI_DIR / "data" / "cache" / "record_materialization" / record_id / "model.urdf"
    if mat.is_file():
        return mat.resolve()
    return None


def _resolve(path, bases):
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    for b in bases:
        cand = (b / p).resolve()
        if cand.is_file():
            return cand
    return (bases[0] / p).resolve()


def build_scene(layout_path, arti_paths):
    """Build the combined render payload for one layout + N arti results.

    ``arti_paths`` is a list of ArtiAgent result JSON paths (each holds
    ``asset_dir`` + ``real_bbox``). Returns ``(scene, mesh_map)`` where
    ``scene["urdfs"]`` is a list of parsed URDFs with *namespaced* mesh keys
    (``u<i>_m<k>``) and ``mesh_map`` maps each key to an absolute mesh file path.
    """
    scene = {}
    errors = []
    mesh_map = {}

    if layout_path and Path(layout_path).is_file():
        try:
            scene["layout"] = load_layout_scene(layout_path)
        except Exception as e:  # noqa: BLE001 - report to the browser
            errors.append("layout: %s" % e)

    urdfs = []
    for i, arti_path in enumerate(arti_paths or []):
        if not arti_path or not Path(arti_path).is_file():
            errors.append("arti[%d]: result JSON not found: %r" % (i, arti_path))
            continue
        try:
            arti = json.loads(Path(arti_path).read_text(encoding="utf-8"))
            urdf_path = resolve_urdf(arti.get("asset_dir"))
            if not urdf_path or not urdf_path.is_file():
                errors.append("arti[%d] (%s): no model.urdf for asset_dir=%r"
                              % (i, Path(arti_path).name, arti.get("asset_dir")))
                continue
            urdf = parse_urdf(urdf_path)
            prefix = "u%d_" % i
            remap = {}
            for m in urdf["meshes"]:
                remap[m["key"]] = prefix + m["key"]
                mesh_map[remap[m["key"]]] = str((urdf_path.parent / m["file"]).resolve())
            for ln in urdf["links"].values():
                for vis in ln["visuals"]:
                    if "mesh_key" in vis:
                        vis["mesh_key"] = remap[vis["mesh_key"]]
            urdf["meshes"] = [{"key": remap[m["key"]], "file": m["file"]} for m in urdf["meshes"]]
            center = arti.get("center") or [0.0, 0.0, 0.0]
            rpy = arti.get("rpy") or [0.0, 0.0, 0.0]
            urdf["center"] = center
            urdf["rpy"] = rpy
            if arti.get("dims") is not None:
                urdf["real_bbox"] = {"center": center, "dims": arti.get("dims")}
            else:
                urdf["real_bbox"] = arti.get("real_bbox")
            urdf["result_name"] = Path(arti_path).stem
            urdfs.append(urdf)
        except Exception as e:  # noqa: BLE001
            errors.append("arti[%d]: %s" % (i, e))

    if urdfs:
        scene["urdfs"] = urdfs
    if errors:
        scene["error"] = "; ".join(errors)
    return scene, mesh_map


# --------------------------------------------------------------------------- #
# HTML / JS
# --------------------------------------------------------------------------- #
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEAL viewer</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #0e0e14; }
  #viewer { position: fixed; inset: 0; left: 230px; }
  #sidebar { position: fixed; top: 0; left: 0; width: 230px; height: 100%; background: rgba(18,18,28,0.95);
             border-right: 1px solid #3a3a4a; z-index: 15; display: flex; flex-direction: column; }
  #sidebar-title { padding: 13px 16px; font-weight: 700; color: #ffd166; border-bottom: 1px solid #3a3a4a; font-size: 14px; }
  #sidebar-list { flex: 1; overflow-y: auto; }
  .obj-btn { display: block; width: 100%; text-align: left; padding: 11px 16px; background: transparent;
             border: none; border-bottom: 1px solid #26262e; color: #ccc; font-size: 13px; cursor: pointer; }
  .obj-btn:hover { background: #26262e; color: #fff; }
  .obj-btn.active { background: #2a2a3a; color: #ffd166; border-left: 3px solid #ffd166; }
  #tooltip { position: fixed; pointer-events: none; display: none; background: rgba(18,18,28,0.92); color: #eaeaea;
             padding: 7px 11px; border-radius: 6px; font-size: 13px; border: 1px solid #3a3a4a; z-index: 10; white-space: nowrap; }
  #tooltip .id { font-weight: 700; color: #ffd166; }
  #tooltip .dim { color: #9aa; font-size: 12px; }
  #tooltip .edges { color: #8ab; font-size: 12px; }
  #legend { position: fixed; bottom: 12px; left: 12px; background: rgba(18,18,28,0.85); color: #bbb;
            padding: 8px 12px; border-radius: 6px; font-size: 12px; z-index: 10; line-height: 1.5; }
  #legend .x { color: #ff4444; } #legend .y { color: #44ff44; } #legend .z { color: #4488ff; }
  #animbtn { position: fixed; top: 12px; right: 12px; background: rgba(24,24,34,0.9); color: #ddd; border: 1px solid #3a3a4a;
             padding: 8px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; z-index: 10; }
  #animbtn:hover { border-color: #ffd166; color: #ffd166; }
  #err { position: fixed; inset: 0; display: none; align-items: center; justify-content: center; color: #ff7777;
         font-size: 15px; z-index: 20; text-align: center; padding: 24px; white-space: pre-wrap; }
</style>
</head>
<body>
<div id="viewer"></div>
<div id="sidebar">
  <div id="sidebar-title">Assets</div>
  <div id="sidebar-list"></div>
</div>
<div id="tooltip"></div>
<div id="legend">layout OBB axes: <span class="x">X</span> &nbsp;<span class="y">Y</span>&nbsp;(up)&nbsp; <span class="z">Z</span></div>
<div id="err"></div>
<button id="animbtn">Animate joints</button>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/OBJLoader.js"></script>
<script>
(function () {
  var err = document.getElementById('err');
  function fail(msg) { err.textContent = msg; err.style.display = 'flex'; }
  if (typeof THREE === 'undefined') { fail('Failed to load Three.js from CDN. Check network access to cdn.jsdelivr.net.'); return; }
  if (typeof THREE.OBJLoader === 'undefined') { fail('Failed to load OBJLoader. Check network access to cdn.jsdelivr.net.'); return; }

  var container = document.getElementById('viewer');
  var tooltip = document.getElementById('tooltip');

  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0x14141e);

  var camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.01, 2000);
  var renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  var d1 = new THREE.DirectionalLight(0xffffff, 0.9); d1.position.set(6, 10, 8); scene.add(d1);
  var d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-6, -4, -8); scene.add(d2);
  var gridHelper = new THREE.GridHelper(1, 10, 0x666666, 0x2a2a2a);
  gridHelper.material.transparent = true;
  gridHelper.material.opacity = 0.5;
  scene.add(gridHelper);
  var axesHelper = new THREE.AxesHelper(1); scene.add(axesHelper);

  var controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  var TYPE_COLORS = { wall: 0x8899aa, floor: 0x559966, door: 0xaa7744, window: 0x6699cc, object: 0xcc9966, box: 0x6688cc };
  var DEG = Math.PI / 180;

  var sceneRoot = new THREE.Group(); scene.add(sceneRoot);
  var layoutGroup = new THREE.Group(); sceneRoot.add(layoutGroup);
  var urdfGroup = new THREE.Group(); sceneRoot.add(urdfGroup);
  // ArtiAgent (and its URDF export) now author models directly in the same y-up / +z-forward
  // frame as LayoutAgent, so no re-orientation is needed. (An older z-up convention required a
  // 180-degree rotation about the (y+z) diagonal; that is no longer the case.)
  var layoutMeshes = [];
  var urdfMeshes = [];
  var layoutEdges = [];

  var axesGroup = new THREE.Group(); scene.add(axesGroup);
  var hovered = null;

  function clearAxes() { while (axesGroup.children.length) axesGroup.remove(axesGroup.children[0]); }
  function showAxes(o) {
    clearAxes();
    var c = new THREE.Vector3(o.center[0], o.center[1], o.center[2]);
    var m = Math.max(o.dims[0], o.dims[1], o.dims[2]);
    var len = Math.max(m * 0.6, 0.15);
    var q = new THREE.Quaternion().setFromEuler(new THREE.Euler(o.theta[0] * DEG, o.theta[1] * DEG, o.theta[2] * DEG, 'XYZ'));
    var ax = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
    var ay = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
    var az = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
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

  function buildLayout(nodes) {
    nodes.forEach(function (o) {
      var w = Math.max(o.dims[0], 1e-3), h = Math.max(o.dims[1], 1e-3), l = Math.max(o.dims[2], 1e-3);
      var geo = new THREE.BoxGeometry(w, h, l);
      var color = TYPE_COLORS[o.type] || 0xcc9966;
      var mat = new THREE.MeshStandardMaterial({ color: color, roughness: 0.6, metalness: 0.05, transparent: true, opacity: 0.55, depthWrite: false });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.quaternion.setFromEuler(new THREE.Euler(o.theta[0] * DEG, o.theta[1] * DEG, o.theta[2] * DEG, 'XYZ'));
      mesh.position.set(o.center[0], o.center[1], o.center[2]);
      mesh.userData = { kind: 'layout', o: o, baseOpacity: 0.55 };
      layoutGroup.add(mesh);
      layoutMeshes.push(mesh);
    });
  }

  function makeMat(color) {
    var c = color || [0.8, 0.8, 0.8, 1.0];
    var mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(c[0], c[1], c[2]), roughness: 0.7, metalness: 0.05 });
    if (c[3] < 1.0) { mat.transparent = true; mat.opacity = c[3]; }
    return mat;
  }

  function instantiate(loaded, color, linkName) {
    var out = new THREE.Group();
    loaded.traverse(function (o) {
      if (o.isMesh) {
        var m = new THREE.Mesh(o.geometry, makeMat(color));
        m.position.copy(o.position);
        m.quaternion.copy(o.quaternion);
        m.scale.copy(o.scale);
        m.userData = { kind: 'urdf', link: linkName };
        out.add(m);
        urdfMeshes.push(m);
      }
    });
    return out;
  }

  function urdfEuler(rpy) { return new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX'); }

  var urdfModels = [];      // one entry per URDF: {name, linkGroups, joints, jointByChild}
  var loadedMeshes = {};

  function loadMesh(key) {
    if (loadedMeshes[key]) return Promise.resolve(loadedMeshes[key]);
    return new Promise(function (resolve, reject) {
      new THREE.OBJLoader().load('/mesh/' + key, function (g) {
        loadedMeshes[key] = g;
        resolve(g);
      }, undefined, function (e) { reject(e); });
    });
  }

  function setJointTransform(model, j, angle) {
    var child = model.linkGroups[j.child];
    if (!child) return;
    var pos = new THREE.Vector3(j.origin.xyz[0], j.origin.xyz[1], j.origin.xyz[2]);
    var quat = new THREE.Quaternion().setFromEuler(urdfEuler(j.origin.rpy));
    var axis = new THREE.Vector3(j.axis[0], j.axis[1], j.axis[2]).normalize();
    if (j.type === 'revolute' || j.type === 'continuous') {
      quat.multiply(new THREE.Quaternion().setFromAxisAngle(axis, angle));
    } else if (j.type === 'prismatic') {
      var dir = axis.clone().applyQuaternion(quat);
      pos.addScaledVector(dir, angle);
    }
    child.position.copy(pos);
    child.quaternion.copy(quat);
  }

  function clampAngle(j) { return Math.min(Math.max(0, j.lower), j.upper); }

  function buildURDF(urdf) {
    var linkGroups = {};
    Object.keys(urdf.links).forEach(function (name) {
      var g = new THREE.Group(); g.name = name; linkGroups[name] = g;
    });
    var joints = urdf.joints || [];
    var jointByChild = {};
    joints.forEach(function (j) { jointByChild[j.child] = j; });
    joints.forEach(function (j) {
      var p = linkGroups[j.parent], c = linkGroups[j.child];
      if (p && c) p.add(c);
    });
    var roots = urdf.roots || [];
    var placed = new THREE.Group();
    if (urdf.center) placed.position.set(urdf.center[0], urdf.center[1], urdf.center[2]);
    if (urdf.rpy) placed.quaternion.setFromEuler(urdfEuler(urdf.rpy));
    roots.forEach(function (r) { if (linkGroups[r]) placed.add(linkGroups[r]); });
    if (!roots.length) {
      Object.keys(linkGroups).forEach(function (n) { if (!jointByChild[n]) placed.add(linkGroups[n]); });
    }
    urdfGroup.add(placed);
    var model = { name: urdf.name, linkGroups: linkGroups, joints: joints, jointByChild: jointByChild, placed: placed };
    urdfModels.push(model);
    joints.forEach(function (j) { setJointTransform(model, j, clampAngle(j)); });

    function primitiveGeometry(p) {
      if (p.type === 'box') {
        return new THREE.BoxGeometry(p.size[0], p.size[1], p.size[2]);
      }
      if (p.type === 'cylinder') {
        // URDF <cylinder> is a column along local +z; three.js CylinderGeometry is along +y.
        var g = new THREE.CylinderGeometry(p.radius, p.radius, p.length, 24);
        g.rotateX(Math.PI / 2);
        return g;
      }
      if (p.type === 'sphere') {
        return new THREE.SphereGeometry(p.radius, 24, 16);
      }
      return null;
    }

    function addVisual(name, vis) {
      var lg = linkGroups[name];
      if (!lg) return Promise.resolve();
      var vg = new THREE.Group();
      vg.position.set(vis.origin.xyz[0], vis.origin.xyz[1], vis.origin.xyz[2]);
      vg.quaternion.setFromEuler(urdfEuler(vis.origin.rpy));
      if (vis.scale) vg.scale.set(vis.scale[0], vis.scale[1], vis.scale[2]);
      if (vis.primitive) {
        var geo = primitiveGeometry(vis.primitive);
        if (geo) {
          var m = new THREE.Mesh(geo, makeMat(vis.color));
          m.userData = { kind: 'urdf', link: name };
          vg.add(m);
          urdfMeshes.push(m);
        }
        lg.add(vg);
        return Promise.resolve();
      }
      return loadMesh(vis.mesh_key).then(function (loaded) {
        vg.add(instantiate(loaded, vis.color, name));
        lg.add(vg);
      });
    }

    var pending = [];
    Object.keys(urdf.links).forEach(function (name) {
      var ln = urdf.links[name];
      (ln.visuals || []).forEach(function (vis) {
        pending.push(addVisual(name, vis));
      });
    });
    return Promise.all(pending);
  }

  function frameAll() {
    var box = new THREE.Box3().setFromObject(sceneRoot);
    if (box.isEmpty()) return;
    var center = box.getCenter(new THREE.Vector3());
    var size = box.getSize(new THREE.Vector3());
    var maxDim = Math.max(size.x, size.y, size.z) || 1;
    var gridSize = Math.max(maxDim * 2.5, 1.0);
    gridHelper.scale.setScalar(gridSize);
    axesHelper.scale.setScalar(gridSize);
    var dist = maxDim * 1.7;
    camera.position.set(center.x + dist * 0.4, center.y + dist * 0.35, center.z + dist);
    camera.near = Math.max(0.001, maxDim / 1000);
    camera.far = maxDim * 60 + 2000;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  var allUrdfs = [];
  var currentIdx = -1;

  function clearUrdf() {
    while (urdfGroup.children.length) urdfGroup.remove(urdfGroup.children[0]);
    urdfModels.length = 0;
    urdfMeshes.length = 0;
  }

  function renderObject(i) {
    if (i < 0 || i >= allUrdfs.length) return;
    clearUrdf();
    buildURDF(allUrdfs[i]).then(function () {
      var u = allUrdfs[i];
      var legend = document.getElementById('legend');
      var parts = ['<span class="x">X</span> right &nbsp;<span class="y">Y</span> up &nbsp;<span class="z">Z</span> front'];
      parts.push(u.name + ' &middot; ' + Object.keys(u.links).length + ' links / ' + (u.joints || []).length + ' joints');
      if (u.real_bbox) {
        parts.push('dims: ' + u.real_bbox.dims.map(function (d) { return d.toFixed(3); }).join(' x ') + ' m');
      }
      legend.innerHTML = parts.join(' &nbsp;&middot;&nbsp; ');
      frameAll();
    });
    var btns = document.querySelectorAll('.obj-btn');
    for (var k = 0; k < btns.length; k++) btns[k].classList.toggle('active', k === i);
    currentIdx = i;
  }

  function renderAll() {
    clearUrdf();
    var pending = [];
    allUrdfs.forEach(function (u) { pending.push(buildURDF(u)); });
    Promise.all(pending).then(function () {
      var legend = document.getElementById('legend');
      var parts = ['<span class="x">X</span> right &nbsp;<span class="y">Y</span> up &nbsp;<span class="z">Z</span> front'];
      parts.push(allUrdfs.length + ' objects');
      legend.innerHTML = parts.join(' &nbsp;&middot;&nbsp; ');
      frameAll();
    });
  }

  function focusObject(i) {
    if (i < 0 || i >= urdfModels.length) return;
    var m = urdfModels[i];
    if (!m.placed) return;
    var box = new THREE.Box3().setFromObject(m.placed);
    if (box.isEmpty()) return;
    var c = box.getCenter(new THREE.Vector3());
    var s = box.getSize(new THREE.Vector3());
    var maxDim = Math.max(s.x, s.y, s.z) || 1;
    camera.position.set(c.x + maxDim * 0.6, c.y + maxDim * 0.5, c.z + maxDim * 1.3);
    controls.target.copy(c);
    controls.update();
    var btns = document.querySelectorAll('.obj-btn');
    for (var k = 0; k < btns.length; k++) btns[k].classList.toggle('active', k === i);
    currentIdx = i;
  }

  fetch('/scene.json').then(function (r) { return r.json(); }).then(function (data) {
    if (data.error) { fail(data.error); return; }
    var hasLayout = !!(data.layout && data.layout.nodes && data.layout.nodes.length);
    if (data.layout) { buildLayout(data.layout.nodes || []); layoutEdges = data.layout.edges || []; }
    allUrdfs = data.urdfs || [];
    var list = document.getElementById('sidebar-list');
    allUrdfs.forEach(function (u, i) {
      var btn = document.createElement('button');
      btn.className = 'obj-btn';
      btn.textContent = u.result_name;
      btn.addEventListener('click', function () {
        if (hasLayout) focusObject(i); else renderObject(i);
      });
      list.appendChild(btn);
    });
    if (allUrdfs.length) {
      if (hasLayout) renderAll(); else renderObject(0);
    } else {
      fail('No assets to render.');
    }
  }).catch(function (e) { fail('Failed to load /scene.json: ' + e); });

  var animateJoints = true;   // auto-play: loop every joint through its [lower, upper] range
  var animStart = performance.now();
  var animBtn = document.getElementById('animbtn');
  animBtn.textContent = 'Pause animation';
  animBtn.addEventListener('click', function () {
    animateJoints = !animateJoints;
    animStart = performance.now();
    this.textContent = animateJoints ? 'Pause animation' : 'Play animation';
  });

  var raycaster = new THREE.Raycaster();
  var pointer = new THREE.Vector2();
  window.addEventListener('mousemove', function (ev) {
    pointer.x = (ev.clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(ev.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    var targets = layoutMeshes.concat(urdfMeshes);
    var hits = raycaster.intersectObjects(targets, false);
    if (hits.length) {
      var mesh = hits[0].object;
      if (mesh.userData.kind === 'layout') {
        // Pick by distance from the mouse ray to each OBB *center* (not the
        // front-most surface), so overlapping/occluded objects stay selectable.
        var best = null, bestDist = Infinity;
        for (var i = 0; i < hits.length; i++) {
          var h = hits[i];
          if (h.object.userData.kind !== 'layout') continue;
          var co = h.object.userData.o;
          var c = new THREE.Vector3(co.center[0], co.center[1], co.center[2]);
          var d = raycaster.ray.distanceToPoint(c);
          if (d < bestDist) { bestDist = d; best = h.object; }
        }
        mesh = best;
        var o = mesh.userData.o;
        setHover(mesh);
        showAxes(o);
        var edgeLines = [];
        layoutEdges.forEach(function (e) {
          if (e.src === o.id) edgeLines.push(e.type + ' → ' + e.dst);
          else if (e.dst === o.id) edgeLines.push(e.type + ' ← ' + e.src);
        });
        tooltip.innerHTML = '<span class="id">' + o.id + '</span>'
          + '<br>type: ' + o.type
          + '<br><span class="dim">' + o.dims.map(function (d) { return d.toFixed(3); }).join(' x ') + ' m</span>'
          + (edgeLines.length ? '<br><span class="edges">' + edgeLines.join('<br>') + '</span>' : '');
      } else {
        setHover(null);
        clearAxes();
        tooltip.innerHTML = '<span class="id">' + mesh.userData.link + '</span><br>link';
      }
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
    if (animateJoints) {
      var t = (performance.now() - animStart) / 1000;
      urdfModels.forEach(function (model) {
        model.joints.forEach(function (j, i) {
          if (j.type === 'fixed' || j.lower === j.upper) return;
          // 0 -> 1 -> 0 loop (closed -> open -> closed), staggered per joint
          var s = 0.5 - 0.5 * Math.cos(t * 1.5 + i * 0.7);
          setJointTransform(model, j, j.lower + (j.upper - j.lower) * s);
        });
      });
    }
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


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    config_path = None     # Path: JSON config re-read on every /scene.json (hot reload)
    cli_layout = None      # --layout CLI override (fixed)
    cli_arti = None        # --arti CLI override (fixed)
    mesh_map = {}          # key -> absolute mesh filename (set by last /scene.json)
    _lock = threading.Lock()

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
        elif path == "/scene.json":
            if Handler.config_path is not None or Handler.cli_layout or Handler.cli_arti:
                layout_path, arti_paths, config_error = _resolve_targets(
                    Handler.config_path, Handler.cli_layout, Handler.cli_arti)
                scene, mesh_map = build_scene(layout_path, arti_paths)
                if config_error:
                    scene["error"] = (scene.get("error") + "; " if scene.get("error") else "") + config_error
            else:
                arti_paths = sorted(ASSET_JSON_DIR.glob("*.json"))
                scene, mesh_map = build_scene(None, arti_paths)
            with Handler._lock:
                Handler.mesh_map = mesh_map
            self._send(200, "application/json; charset=utf-8", json.dumps(scene).encode("utf-8"))
        elif path.startswith("/mesh/"):
            self._serve_mesh(path[len("/mesh/"):])
        else:
            self._send(404, "text/plain", b"not found")

    def _serve_mesh(self, key):
        with Handler._lock:
            filename = Handler.mesh_map.get(key)
        if not filename:
            self._send(404, "text/plain", b"mesh not found")
            return
        full = Path(filename)
        if not full.is_file():
            self._send(404, "text/plain", b"mesh file missing")
            return
        self._send(200, "text/plain; charset=utf-8", full.read_bytes())

    def log_message(self, fmt, *args):
        pass  # quiet


def _most_recent(subdir):
    d = OUTPUT_DIR / subdir
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _resolve_targets(config_path, cli_layout, cli_arti):
    """Re-read the config (if any) and resolve the current layout/arti targets.

    Precedence: CLI --layout/--arti override the config file; if neither is set
    anywhere, the most recently written output from each agent is auto-discovered.
    Returns (layout_path, arti_paths, config_error): ``layout_path`` is a resolved
    Path or None, ``arti_paths`` is a list of resolved Paths (possibly empty), and
    ``config_error`` is a config read/parse error string (or None).
    """
    layout = cli_layout
    arti = cli_arti
    bases = [BASE_ROOT, OUTPUT_DIR]
    config_error = None

    if config_path is not None:
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            cfg = {}
            config_error = "cannot read %s: %s" % (config_path, e)
        bases = [config_path.parent, BASE_ROOT, OUTPUT_DIR]
        if layout is None:
            layout = cfg.get("layout")
        if arti is None:
            arti = cfg.get("arti")

    if layout is None and arti is None:
        layout = _most_recent("layoutagent")
        arti = _most_recent("artiagent")

    if isinstance(arti, list):
        arti_list = arti
    elif arti:
        arti_list = [arti]
    else:
        arti_list = []

    layout_path = _resolve(layout, bases) if layout else None
    arti_paths = [_resolve(a, bases) for a in arti_list]
    return layout_path, arti_paths, config_error


def main():
    ap = argparse.ArgumentParser(description="Serve a Three.js viewer for SEAL outputs (layout + URDF)")
    ap.add_argument("--config", help='JSON file: {"layout": <path>, "arti": <path or [paths]>} (paths relative to BaseAgent/output/ or absolute)')
    ap.add_argument("--layout", help="Path to a LayoutAgent scene-graph JSON (overrides --config layout)")
    ap.add_argument("--arti", help="Path to an ArtiAgent result JSON (overrides --config arti)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = ap.parse_args()

    config_path = Path(args.config).expanduser().resolve() if args.config else None
    Handler.config_path = config_path
    Handler.cli_layout = args.layout
    Handler.cli_arti = args.arti

    # resolve once for a startup summary (the same resolution re-runs on every page load)
    layout_path, arti_paths, config_error = _resolve_targets(config_path, args.layout, args.arti)
    if config_error:
        print("config:", config_error, file=sys.stderr)
    if layout_path is not None and layout_path.is_file():
        print("layout:", layout_path, flush=True)
    for ap_ in arti_paths:
        if ap_ is not None and ap_.is_file():
            print("arti:  ", ap_, flush=True)
    if layout_path is None and not arti_paths:
        print("(no layout/arti selected; will auto-discover or render nothing)", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("room_viewer serving on http://%s:%d/  (edit --config and refresh to hot-reload)" % (args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)


if __name__ == "__main__":
    main()
