uniform sampler2D uPosition;
uniform sampler2D uNormal;
vec4 positionAt(ivec2 xy) { return texelFetch(uPosition,xy,0); }
vec3 normalAt(ivec2 xy) { return texelFetch(uNormal,xy,0).xyz; }
