#version 430 core
#include "views.glsl"
#include "camera.glsl"
#include "gbuffer.glsl"
#include "receiver.glsl"
uniform sampler2D uSignal,uDetails;
layout(location=0) out vec4 image;
void main() {
    camera();
    ivec2 xy=ivec2(gl_FragCoord.xy);
    vec4 g=positionAt(xy), diag=texelFetch(uDetails,xy,0);
    vec3 o,d,primary=primaryRay(xy);
    vec3 c=g.w>0?material(int(g.w),g.xyz,normalAt(xy)):sky(primary);
    if(reflectionRay(xy,g,o,d)) {
        vec3 reflected=texelFetch(uSignal,xy,0).rgb;
        float facing=clamp(abs(primary.y),0.0,1.0);
        float fresnel=.045+.955*pow(1.0-facing,5.0);
        c=uScene==3?.89*reflected:mix(vec3(.053,.18,.19),reflected,.27+.73*fresnel);
        if(uDisplay==1) c=reflected;
        if(uDisplay==2) c=vec3(diag.w/4.0,diag.z/(uBudget+5.0),.045);
    } else if(uDisplay!=0) c=vec3(.025);
    image=vec4(toDisplay(c),1);
}
