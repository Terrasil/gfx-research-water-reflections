Hit trace(vec3 o,vec3 d,float limit) {
    Hit hit=miss(limit);
    if(uScene==4) return hit; // Empty-environment control.
    groundHit(o,d,-1.35,hit);
    if(uScene==0 || uScene==3) {
        boxHit(o,d,vec3(-1.36,.88,-1.8),vec3(.85,.96,.64),2,hit);
        boxHit(o,d,vec3(1.05,1.25,-3.1),vec3(.92,1.32,.67),3,hit);
        boxHit(o,d,vec3(-.20,.22,-.72),vec3(2.95,.21,.55),4,hit);
        sphereHit(o,d,vec3(.42,1.04,-.72),.61,5,hit);
        boxHit(o,d,vec3(-.7,1.0,-5.85),vec3(4.9,1.1,.47),6,hit);
    } else if(uScene==1) {
        for(int i=0;i<10;++i)
            boxHit(o,d,vec3(-2.8+.61*i,.91,-1.5),vec3(.055,1.0,.10),i+2,hit);
        boxHit(o,d,vec3(0,1.56,-1.64),vec3(3.05,.065,.11),12,hit);
        boxHit(o,d,vec3(0,.75,-4.0),vec3(3.65,.81,.28),13,hit);
        sphereHit(o,d,vec3(.62,1.35,-3.45),.64,14,hit);
    } else {
        boxHit(o,d,vec3(-2.4,.93,-1.45),vec3(1.45,.98,.19),2,hit);
        boxHit(o,d,vec3(2.62,1.62,-2.6),vec3(.34,1.7,1.85),3,hit);
        boxHit(o,d,vec3(-4.4,2.0,2.8),vec3(.62,2.1,.76),4,hit);
        sphereHit(o,d,vec3(.48,1.22,-3.45),1.14,5,hit);
        boxHit(o,d,vec3(.35,.22,.56),vec3(.10,.25,.92),6,hit);
    }
    return hit;
}
float contactMask(vec3 p,int id) { return 0; }
