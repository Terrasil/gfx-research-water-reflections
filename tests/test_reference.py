"""Independent double-precision ray tests for the default scene and its geometric reference."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from renderer import Renderer
from protocol import STUDY

def unit(x):
    a=np.asarray(x,dtype=float)
    return a/np.linalg.norm(a)

def intersect(o,d,limit,boxes,spheres,ground):
    hits=[]
    if abs(d[1])>1e-12:
        hits.append(((ground-o[1])/d[1],1))
    for ident,cen,half in boxes:
        # Intersect the six finite faces directly, independently of the GLSL slab code.
        for axis in range(3):
            if abs(d[axis])<1e-12: continue
            for sign in (-1,1):
                t=(cen[axis]+sign*half[axis]-o[axis])/d[axis]
                p=np.abs(o+t*d-cen)
                if all(p[k]<=half[k]+1e-8 for k in range(3) if k!=axis):
                    hits.append((t,ident))
    for ident,cen,r in spheres:
        delta=o-cen
        b=np.dot(d,delta)
        disc=b*b-np.dot(delta,delta)+r*r
        if disc>=0:
            hits.extend([(float(-b-np.sqrt(disc)),ident),(float(-b+np.sqrt(disc)),ident)])
    return min(((t,k) for t,k in hits if 1e-4<t<limit),default=(limit,0))

def test():
    ao=STUDY["kind"]=="ao"
    if ao:
        eye=np.array([4.1,3.1,6.9]); target=(0,.65,-.4); ground=0.
        boxes=[(2,(-1.3,.9,-.1),(.84,.9,.84)),(4,(1.82,.73,-1.25),(.75,.73,.72)),
               (5,(-.1,.65,-2.5),(1.55,.65,.28)),(6,(-1,.18,1.55),(.75,.18,.29))]
        spheres=[(3,(.48,.56,.42),.56)]
    else:
        eye=np.array([2.4,2.1,7.8]); target=(0,.44,-1); ground=-1.35
        boxes=[(2,(-1.36,.88,-1.8),(.85,.96,.64)),(3,(1.05,1.25,-3.1),(.92,1.32,.67)),
               (4,(-.20,.22,-.72),(2.95,.21,.55)),(6,(-.7,1,-5.85),(4.9,1.1,.47))]
        spheres=[(5,(.42,1.04,-.72),.61)]
    boxes=[(k,np.array(c),np.array(h)) for k,c,h in boxes]
    spheres=[(k,np.array(c),r) for k,c,r in spheres]
    forward=unit(target-eye); right=unit(np.cross(forward,(0,1,0))); up=np.cross(right,forward)
    w,h=120,80
    r=Renderer("auto",None)
    r.configure(dict(scene=0,view=0,parameter=1.5 if ao else 0.,size=[w,h]),17)
    g=r.read("scene"); signal,info,shifts=r.reference(256,17)
    normals=r.read("scene",1)
    count=0; secondary=0
    for y in range(3,h,6):
        for x in range(4,w,7):
            film=np.array([2*x+1-w, h-2*y-1])/h
            d=unit(forward+np.tan(np.deg2rad(25))*(film[0]*right+film[1]*up))
            t,k=intersect(eye,d,90.,boxes,spheres,ground)
            assert int(g[y,x,3])==k and np.linalg.norm(g[y,x,:3]-(eye+t*d))<.003
            count+=1
            if not ao and d[1]<-.00001:
                water=-eye[1]/d[1]
                if 0<water<t:
                    o=eye+water*d+np.array([0,.008,0])
                    refd=d.copy();refd[1]*=-1
                    t2,k2=intersect(o,refd,35.,boxes,spheres,ground)
                    assert int(info[y,x,0])==k2
                    if k2: assert abs(info[y,x,1]-t2)<.002
                    secondary+=1
    if ao:
        # A second cosine estimator uses NumPy PCG64, independent directions and face intersections.
        rng=np.random.default_rng(8835)
        tests=[(h//2,w//2),(int(h*.72),int(w*.41)),(int(h*.65),int(w*.6))]
        for y,x in tests:
            p=g[y,x,:3].astype(float)
            assert g[y,x,3]>0
            n=unit(normals[y,x,:3]); a=unit(np.cross(n,(1,0,0) if abs(n[0])<.9 else (0,1,0)))
            b=np.cross(n,a); visible=0
            for u,v in rng.random((2048,2)):
                d=np.sqrt(u)*(a*np.cos(2*np.pi*v)+b*np.sin(2*np.pi*v))+n*np.sqrt(1-u)
                visible+=intersect(p+.0045*n,d,1.5,boxes,spheres,ground)[1]==0
            assert abs(visible/2048-signal[y,x])<.08
            secondary+=1
    assert secondary>0
    print(f"Verified {count} primary rays and {secondary} independent secondary checks.")

if __name__=="__main__":
    test()
