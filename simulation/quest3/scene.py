"""Export MuJoCo's compiled visual geometry, in its actual local geom frames."""
import gzip,json
import numpy as np
import mujoco

def export_scene(engine):
    m=engine.m;meshes={};geoms=[];triangles=0
    for gid in engine.visible:
        kind=int(m.geom_type[gid]);mid=int(m.geom_dataid[gid]);mat=int(m.geom_matid[gid])
        rgba=m.mat_rgba[mat] if mat>=0 else m.geom_rgba[gid]
        geoms.append({'id':gid,'name':m.geom(gid).name,'type':kind,'mesh':mid,'size':m.geom_size[gid].tolist(),'rgba':rgba.tolist()})
        if kind==int(mujoco.mjtGeom.mjGEOM_MESH) and str(mid) not in meshes:
            va=int(m.mesh_vertadr[mid]);vn=int(m.mesh_vertnum[mid]);fa=int(m.mesh_faceadr[mid]);fn=int(m.mesh_facenum[mid])
            meshes[str(mid)]={'vertices':m.mesh_vert[va:va+vn].round(6).reshape(-1).tolist(),'indices':m.mesh_face[fa:fa+fn].reshape(-1).tolist()}
            triangles+=fn
    scene={'schema':1,'frame':'mujoco_world_meters_z_up','geoms':geoms,'meshes':meshes,'mesh_triangles':triangles,'task':engine.info,
           'view':'third_person_simulation','initial_state':engine.snapshot()}
    raw=json.dumps(scene,separators=(',',':'),allow_nan=False).encode('utf-8')
    return gzip.compress(raw),{'geoms':len(geoms),'meshes':len(meshes),'mesh_triangles':triangles,'uncompressed_bytes':len(raw)}
