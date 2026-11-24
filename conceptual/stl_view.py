"""Draw an STL mesh in four views (matplotlib only); a display aid for OpenVSP exports.

    python -m conceptual.stl_view MODEL.stl OUT.png "title"
"""
import sys, struct, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
p=sys.argv[1]; raw=open(p,'rb').read()
if raw[:5]==b'solid' and b'facet' in raw[:300]:
    v=[];cur=[]
    for line in raw.decode().splitlines():
        t=line.split()
        if t and t[0]=='vertex': cur.append([float(x) for x in t[1:4]])
        if len(cur)==3: v.append(cur); cur=[]
    tri=np.array(v)
else:
    n=struct.unpack('<I',raw[80:84])[0]; a=np.frombuffer(raw[84:84+n*50],dtype=np.dtype([('n','<3f4'),('v','<9f4'),('a','<u2')]))
    tri=a['v'].reshape(-1,3,3).astype(float)
print(len(tri),"triangles", tri.reshape(-1,3).min(0), tri.reshape(-1,3).max(0))
L=np.array([-0.4,-0.5,0.75]);L/=np.linalg.norm(L)
nrm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);nrm/=np.linalg.norm(nrm,axis=1,keepdims=True)+1e-12
sh=0.35+0.65*np.abs(nrm@L)
fig=plt.figure(figsize=(16,10)); fig.subplots_adjust(0,0,1,0.94,0,0)
views=[(25,-130,"Three-quarter, front left"),(20,40,"Rear right"),(90,-90,"Top"),(0,-90,"Side")]
lo,hi=tri.reshape(-1,3).min(0),tri.reshape(-1,3).max(0);c=(lo+hi)/2;r=(hi-lo).max()/2
for k,(el,az,t) in enumerate(views):
    ax=fig.add_subplot(2,2,k+1,projection='3d')
    col=np.clip(np.outer(sh,[0.75,0.78,0.85]),0,1)
    ax.add_collection3d(Poly3DCollection(tri,facecolors=col,edgecolors='none'))
    for i,f in enumerate((ax.set_xlim,ax.set_ylim,ax.set_zlim)): f(c[i]-r,c[i]+r)
    ax.set_box_aspect((1,1,1), zoom=1.9); ax.view_init(el,az); ax.set_axis_off(); ax.set_title(t)
fig.suptitle(sys.argv[3]); fig.savefig(sys.argv[2],dpi=110,bbox_inches="tight")
