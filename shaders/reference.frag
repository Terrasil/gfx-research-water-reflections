#version 430 core
#include "views.glsl"
#include "camera.glsl"
#include "geometry.glsl"
#include "objects.glsl"
#include "gbuffer.glsl"
#include "receiver.glsl"
layout(location=0) out vec4 signal;
layout(location=1) out vec4 details;
void main() {
    camera();
    ivec2 xy=ivec2(gl_FragCoord.xy);
    vec3 o,d;
    signal=vec4(0,0,0,1); details=vec4(-1,0,0,0);
    if(!reflectionRay(xy,positionAt(xy),o,d)) return;
    Hit h=trace(o,d,traceLimit);
    signal.rgb=sky(d); details=vec4(0,0,1,0);
    if(h.id==0) return;
    vec3 world=o+h.t*d; ivec2 uv;
    float tol=max(.03,2.0*pixelSize(world));
    int type=2;
    if(screenPixel(world,uv)) {
        vec4 first=positionAt(uv);
        type=(int(first.w)==h.id && length(first.xyz-world)<=tol)?4:3;
    }
    signal.rgb=material(h.id,world,h.n);
    details=vec4(float(h.id),h.t,float(type),tol);
}
