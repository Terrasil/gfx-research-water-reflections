uniform ivec2 uSize;
uniform int uScene, uView, uBudget, uMethod, uDisplay, uSeed;
uniform float uParameter;
const float pi = 3.141592653589793;
const float tanHalfFov = 0.46630766; // 50 degree vertical field of view
const float farLimit = 90.0;
vec3 eye, forward, rightAxis, upAxis;

void camera() {
    vec3 target;
    setView(uScene, uView, eye, target);
    forward = normalize(target - eye);
    rightAxis = normalize(cross(forward, vec3(0,1,0)));
    upAxis = cross(rightAxis, forward);
}
float zView(vec3 p) { return dot(p - eye, forward); }
float pixelSize(vec3 p) { return 2.0 * tanHalfFov * max(zView(p), 0.01) / float(uSize.y); }
vec3 primaryRay(ivec2 xy) {
    vec2 film = (2.0 * (vec2(xy) + 0.5) - vec2(uSize)) / float(uSize.y);
    return normalize(forward + tanHalfFov * (film.x * rightAxis + film.y * upAxis));
}
vec2 filmUV(vec3 p) {
    vec3 v = p - eye;
    vec2 k = vec2(dot(v, rightAxis) * float(uSize.y) / float(uSize.x), dot(v, upAxis));
    return 0.5 + 0.5 * k / (tanHalfFov * dot(v, forward));
}
bool screenPixel(vec3 p, out ivec2 xy) {
    if (zView(p) <= 0.02) return false;
    vec2 uv = filmUV(p);
    if (any(lessThan(uv, vec2(0))) || any(greaterThanEqual(uv, vec2(1)))) return false;
    xy = ivec2(uv * vec2(uSize));
    return true;
}
bool inside(ivec2 xy) {
    return all(greaterThanEqual(xy, ivec2(0))) && all(lessThan(xy, uSize));
}
vec3 sky(vec3 d) {
    return mix(vec3(0.66,0.78,0.85), vec3(0.17,0.34,0.52), smoothstep(-0.05,0.85,d.y));
}
vec3 material(int id, vec3 p, vec3 n) {
    const vec3 colors[7] = vec3[7](vec3(.41,.48,.43), vec3(.61,.22,.11), vec3(.19,.35,.41),
        vec3(.69,.50,.26), vec3(.23,.38,.30), vec3(.48,.42,.34), vec3(.63,.66,.55));
    vec3 base = colors[(id-1)%7];
    float tiles = mod(floor(p.x*1.2)+floor(p.z*1.2),2.0);
    if(id==1) base *= mix(.86,1.0,tiles);
    return base * (.53 + .47*max(0.0,dot(n,normalize(vec3(-.6,1,.45)))));
}
vec3 toDisplay(vec3 c) {
    c=max(c,vec3(0));
    return mix(12.92*c,1.055*pow(c,vec3(1.0/2.4))-.055,greaterThan(c,vec3(.0031308)));
}
