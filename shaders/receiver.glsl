const float traceLimit=35.0;
bool reflectionRay(ivec2 xy,vec4 front,out vec3 o,out vec3 d) {
    vec3 primary=primaryRay(xy);
    bool metal=uScene==3;
    vec3 baseN=metal?normalize(vec3(0,1,.30)):vec3(0,1,0);
    vec3 anchor=metal?vec3(0,.56,1.25):vec3(0);
    float denom=dot(primary,baseN);
    if(denom>=-1e-5) return false;
    float t=dot(anchor-eye,baseN)/denom;
    if(t<=0.02 || t>=farLimit || (front.w>0 && t>=length(front.xyz-eye))) return false;
    vec3 p=eye+t*primary;
    if(metal && (abs(p.x)>3.4 || abs(p.z-anchor.z)>2.0)) return false;
    vec3 n=baseN;
    if(!metal) {
        float gx=.85*cos(1.7*p.x+.74*p.z)+.38*cos(3.1*p.x-1.9*p.z+.4);
        float gz=.37*cos(1.7*p.x+.74*p.z)-.22*cos(3.1*p.x-1.9*p.z+.4);
        n=normalize(vec3(-uParameter*gx,1,-uParameter*gz));
    }
    o=p+.008*baseN; d=normalize(reflect(primary,n));
    return true;
}
