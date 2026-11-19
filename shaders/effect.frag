#version 430 core
#include "views.glsl"
#include "camera.glsl"
#include "gbuffer.glsl"
#include "receiver.glsl"
layout(location=0) out vec4 signal;
#ifdef DIAGNOSTICS
layout(location=1) out vec4 details;
#endif
struct Sample { float t; float f; ivec2 xy; vec4 surface; };
int probes=0, midpoints=0;
Sample probe(vec3 o,vec3 d,float t) {
    ++probes;
    vec3 x=o+t*d;
    ivec2 xy=ivec2(0);
    vec4 p=vec4(0);
    if(screenPixel(x,xy)) p=positionAt(xy);
    return Sample(t,p.w>0?zView(x)-zView(p.xyz):-farLimit,xy,p);
}
bool accepted(Sample s) {
    return s.surface.w>0 && abs(s.f)<=max(.015,1.5*pixelSize(s.surface.xyz));
}
bool clipHalfspace(float a,float b,inout float lo,inout float hi) {
    if(abs(b)<1e-8) return a>=0;
    float t=-a/b;
    if(b>0) lo=max(lo,t); else hi=min(hi,t);
    return lo<hi;
}
bool clipRay(vec3 o,vec3 d,out float lo,out float hi) {
    lo=.012; hi=traceLimit;
    vec3 v=o-eye;
    float z=dot(v,forward), dz=dot(d,forward);
    float tx=tanHalfFov*float(uSize.x)/float(uSize.y);
    for(int s=-1;s<=1;s+=2) {
        if(!clipHalfspace(tx*z+s*dot(v,rightAxis),tx*dz+s*dot(d,rightAxis),lo,hi)) return false;
        if(!clipHalfspace(tanHalfFov*z+s*dot(v,upAxis),tanHalfFov*dz+s*dot(d,upAxis),lo,hi)) return false;
    }
    return clipHalfspace(z-.021,dz,lo,hi);
}
float projectiveT(float s,float a,float b,float za,float zb) {
    return mix(a/za,b/zb,s)/mix(1.0/za,1.0/zb,s);
}
bool tangentStep(Sample s,vec3 o,vec3 d,out float next) {
    if(s.surface.w<=0) return false;
    vec3 n=normalAt(s.xy);
    float divisor=dot(n,d);
    if(abs(divisor)<.002) return false;
    next=dot(n,s.surface.xyz-o)/divisor;
    return !(isnan(next)||isinf(next));
}
bool solve(vec3 o,vec3 d,out Sample answer) {
    float lo,hi;
    if(!clipRay(o,d,lo,hi)) return false;
    float za=zView(o+lo*d), zb=zView(o+hi*d);
    // A deliberately unbracketed comparator with the same six-update ceiling at both budgets.
    if(uMethod==4) {
        float t=projectiveT(.35,lo,hi,za,zb);
        for(int k=0;k<=6;++k) {
            Sample s=probe(o,d,t);
            if(accepted(s)) { answer=s; return true; }
            float next;
            if(!tangentStep(s,o,d,next) || next<=lo || next>=hi || abs(next-t)<1e-5) return false;
            t=next;
        }
        return false;
    }
    Sample a=probe(o,d,lo);
    if(accepted(a)) { answer=a; return true; }
    for(int j=1;j<=uBudget;++j) {
        float f=float(j)/float(uBudget);
        float t=uMethod==0?mix(lo,hi,f):projectiveT(f,lo,hi,za,zb);
        Sample b=probe(o,d,t);
        if(accepted(b)) { answer=b; return true; }
        if(a.f<0.0 && b.f>=0.0) {
            // First sign change is a depth-buffer bracket. A jump can mimic a root.
            for(int k=0;k<4;++k) {
                float next=.5*(a.t+b.t), proposal=next; bool use=false;
                if(uMethod==2 && a.surface.w>0 && b.surface.w>0)
                    { proposal=(a.t*b.f-b.t*a.f)/(b.f-a.f); use=true; }
                if(uMethod==3) {
                    Sample support=b;
                    if(a.surface.w>0 && abs(a.f)<abs(b.f)) support=a;
                    use=tangentStep(support,o,d,proposal);
                }
                if(use && proposal>a.t+1e-5 && proposal<b.t-1e-5) next=proposal;
                else if(uMethod==2 || uMethod==3) ++midpoints;
                Sample s=probe(o,d,next);
                if(accepted(s)) { answer=s; return true; }
                if(s.f<0) a=s; else b=s;
            }
            return false;
        }
        a=b;
    }
    return false;
}
void main() {
    camera();
    ivec2 xy=ivec2(gl_FragCoord.xy);
    vec4 g=positionAt(xy);
    vec3 o,d,color=vec3(0); float id=-1, distanceT=0;
    if(reflectionRay(xy,g,o,d)) {
        color=sky(d); id=0;
        Sample hit;
        if(solve(o,d,hit)) {
            id=hit.surface.w; distanceT=hit.t;
            color=material(int(id),hit.surface.xyz,normalAt(hit.xy));
        }
    }
    signal=vec4(color,1);
#ifdef DIAGNOSTICS
    details=vec4(id,distanceT,float(probes),float(midpoints));
#endif
}
