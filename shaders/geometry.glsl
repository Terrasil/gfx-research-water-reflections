struct Hit { float t; vec3 n; int id; };
const float rayEps = 0.0001;
Hit miss(float limit) { return Hit(limit,vec3(0),0); }

void boxHit(vec3 o, vec3 d, vec3 center, vec3 halfSize, int id, inout Hit best) {
    vec3 lo = center-halfSize, hi = center+halfSize;
    float enter = -1e20, leave = best.t;
    vec3 enterN=vec3(0), leaveN=vec3(0);
    for(int k=0;k<3;++k) {
        if(abs(d[k]) < 1e-8) {
            if(o[k]<lo[k] || o[k]>hi[k]) return;
            continue;
        }
        float a=(lo[k]-o[k])/d[k], b=(hi[k]-o[k])/d[k];
        vec3 n=vec3(0); n[k]=-sign(d[k]);
        float nearT=min(a,b), farT=max(a,b);
        if(nearT>enter) { enter=nearT; enterN=n; }
        if(farT<leave) { leave=farT; leaveN=-n; }
        if(enter>leave) return;
    }
    bool outside=enter>rayEps;
    float t=outside?enter:leave;
    if(t>rayEps && t<best.t) best=Hit(t,outside?enterN:leaveN,id);
}
void sphereHit(vec3 o,vec3 d,vec3 center,float r,int id,inout Hit best) {
    vec3 s=o-center;
    float b=dot(s,d), disc=b*b-dot(s,s)+r*r;
    if(disc<0.0) return;
    float h=sqrt(disc), t=-b-h;
    if(t<=rayEps) t=-b+h;
    if(t>rayEps && t<best.t) best=Hit(t,(s+t*d)/r,id);
}
void groundHit(vec3 o,vec3 d,float height,inout Hit best) {
    if(abs(d.y)<1e-8) return;
    float t=(height-o.y)/d.y;
    if(t>rayEps && t<best.t) best=Hit(t,vec3(0,1,0),1);
}
