// Synthetic camera stress in display pixels; not a calibrated camera/flight model.
import * as THREE from './vendor/three.module.js';

export function cameraEffects(renderer) {
 const target=new THREE.WebGLRenderTarget(1280,720,{depthBuffer:true});
 const uniforms={frame:{value:target.texture},resolution:{value:new THREE.Vector2(1280,720)},
  exposure:{value:1},blur:{value:0},noise:{value:0},vignette:{value:0},distortion:{value:0},glare:{value:0},jitter:{value:0},seed:{value:0},
  calibrated:{value:0},intrinsics:{value:new THREE.Vector4()},lens:{value:new THREE.Vector4()},k3:{value:0},
  shutter:{value:new THREE.Vector2()},integration:{value:new THREE.Vector2()}};
 const material=new THREE.ShaderMaterial({uniforms,depthTest:false,depthWrite:false,
  vertexShader:`varying vec2 uv0; void main(){uv0=uv;gl_Position=vec4(position.xy,0.,1.);}`,
  fragmentShader:`
   uniform sampler2D frame;
   uniform vec2 resolution;
   uniform float exposure,blur,noise,vignette,distortion,glare,jitter,seed;
   uniform float calibrated,k3;
   uniform vec4 intrinsics,lens;
   uniform vec2 shutter,integration;
   varying vec2 uv0;
   float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7))+seed)*43758.5453);}
   void main(){
    vec2 p=uv0-.5;
    vec2 uv=.5+p*(1.+distortion*dot(p,p)*4.);
    if(calibrated>.5){
     vec2 pixel=vec2(uv0.x,1.-uv0.y)*resolution;
     vec2 observed=(pixel-intrinsics.zw)/intrinsics.xy,x=observed;
     for(int i=0;i<15;i++){
      float r2=dot(x,x),radial=1.+lens.x*r2+lens.y*r2*r2+k3*r2*r2*r2;
      vec2 tangential=vec2(2.*lens.z*x.x*x.y+lens.w*(r2+2.*x.x*x.x),lens.z*(r2+2.*x.y*x.y)+2.*lens.w*x.x*x.y);
      x+=observed-(x*radial+tangential);
     }
     pixel=x*intrinsics.xy+intrinsics.zw+shutter*(pixel.y/resolution.y-.5);
     uv=vec2(pixel.x/resolution.x,1.-pixel.y/resolution.y);
    }
    uv+=vec2(sin(seed*1.7),cos(seed*.7))*jitter;
    vec2 d=vec2(blur,blur*.27)/resolution;
    if(calibrated>.5)d+=vec2(integration.x,-integration.y)/resolution*.25;
    vec3 c=texture2D(frame,uv).rgb*.28;
    c+=texture2D(frame,uv+d).rgb*.22+texture2D(frame,uv-d).rgb*.22;
    c+=texture2D(frame,uv+2.*d).rgb*.14+texture2D(frame,uv-2.*d).rgb*.14;
    c*=exposure*(1.-vignette*dot(p,p)*2.);
    float flare=exp(-dot(uv0-vec2(.76,.82),uv0-vec2(.76,.82))*9.);
    c+=glare*flare*vec3(.85,.78,.6);
    c+=(hash(floor(uv0*resolution))-.5)*noise;
    gl_FragColor=vec4(max(c,vec3(0.)),1.);
    #include <colorspace_fragment>
   }`});
 const screen=new THREE.Scene();screen.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),material));
 const camera=new THREE.Camera();
 return {
  configure(profile,seed){
   target.setSize(profile.width,profile.height);uniforms.resolution.value.set(profile.width,profile.height);
   for(const name of ['exposure','blur','noise','vignette','distortion','glare','jitter'])uniforms[name].value=profile.effects?.[name]??(name==='exposure'?1:0);
   uniforms.seed.value=seed%10000;
   const c=profile.optics;uniforms.calibrated.value=c?1:0;
   if(c){
    uniforms.intrinsics.value.set(c.fx,c.fy,c.cx,c.cy);uniforms.lens.value.set(...c.distortion.slice(0,4));uniforms.k3.value=c.distortion[4];
    const flow=profile.rotational_flow_px_s||[0,0];
    uniforms.shutter.value.set(flow[0]*c.rolling_shutter_ms/1000,flow[1]*c.rolling_shutter_ms/1000);
    uniforms.integration.value.set(flow[0]*c.exposure_ms/1000,flow[1]*c.exposure_ms/1000);
   }
  },
  render(scene,camera3d){
   renderer.setRenderTarget(target);renderer.render(scene,camera3d);
   renderer.setRenderTarget(null);renderer.render(screen,camera);
  }
 };
}
