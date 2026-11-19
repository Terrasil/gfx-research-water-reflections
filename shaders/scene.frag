#version 430 core
#include "views.glsl"
#include "camera.glsl"
#include "geometry.glsl"
#include "objects.glsl"
layout(location=0) out vec4 positionId;
layout(location=1) out vec4 normalContact;
void main() {
    camera();
    vec3 d=primaryRay(ivec2(gl_FragCoord.xy));
    Hit hit=trace(eye,d,farLimit);
    vec3 p=eye+hit.t*d;
    positionId=vec4(p,float(hit.id));
    normalContact=vec4(hit.n,contactMask(p,hit.id));
}
