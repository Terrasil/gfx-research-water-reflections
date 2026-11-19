void setView(int scene,int view,out vec3 e,out vec3 target) {
    const vec3 eyes[3]=vec3[3](vec3(2.4,2.1,7.8),vec3(-3.1,1.5,7.2),vec3(.6,.98,7.4));
    e=eyes[view]; target=vec3(0,.44,-1.0);
    if(scene==2) { e.x+=1.4; target.x+=.8; }
    if(scene==3) { e.y+=.9; target.y+=.25; }
}
