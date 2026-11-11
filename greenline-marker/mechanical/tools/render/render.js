// GL-1 renderer: headless Chromium (Playwright, SwiftShader) + three.js r160, driven by a JSON config.
//   node render.js config.json
// config: { out, width, height, eye:[x,y,z], target:[x,y,z], up:[x,y,z], fov | ortho (half height in mm), background,
//           title, subtitle, footer,
//           parts:[ { stl, color:[r,g,b], opacity, offset:[x,y,z], rotZ180About:[cx,cy], edges:true, edgeColor:[r,g,b],
//                     capColor:[r,g,b] } ],
//           capPlanes:[ {axis:'x'|'y'|'z', value} ]   triangles lying on these planes are drawn in the part's capColor,
//           labels:[ { text, anchor:[x,y,z], side:'L'|'R' } ] }
// three.js is looked for in ./node_modules (npm install three@0.160.0) and in the session scratchpad.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

function findThree() {
  const cands = [path.join(__dirname, 'node_modules/three/build/three.min.js'),
    '/tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/render/node_modules/three/build/three.min.js'];
  if (process.env.THREE_MIN_JS) cands.unshift(process.env.THREE_MIN_JS);
  for (const c of cands) if (fs.existsSync(c)) return fs.readFileSync(c, 'utf8');
  throw new Error('three.min.js not found: run "npm install three@0.160.0" in ' + __dirname);
}

const PAGE_SCRIPT = String.raw`
function parseSTL(buf){const dv=new DataView(buf);const n=dv.getUint32(80,true);const pos=new Float32Array(n*9);let o=84;
  for(let i=0;i<n;i++){o+=12;for(let j=0;j<9;j++){pos[i*9+j]=dv.getFloat32(o,true);o+=4;}o+=2;}return pos;}
// smooth shading across faces that meet at less than the crease angle (cylinders, fillets), flat across sharp edges
function creaseNormals(pos,angleDeg){const n=pos.length/9;const fn=new Float32Array(n*3);const cosT=Math.cos(angleDeg*Math.PI/180);
  for(let i=0;i<n;i++){const ax=pos[i*9+3]-pos[i*9],ay=pos[i*9+4]-pos[i*9+1],az=pos[i*9+5]-pos[i*9+2];
    const bx=pos[i*9+6]-pos[i*9],by=pos[i*9+7]-pos[i*9+1],bz=pos[i*9+8]-pos[i*9+2];
    fn[i*3]=ay*bz-az*by;fn[i*3+1]=az*bx-ax*bz;fn[i*3+2]=ax*by-ay*bx;}          // area-weighted face normal
  const map=new Map();
  for(let i=0;i<n*3;i++){const k=Math.round(pos[i*3]*2000)+','+Math.round(pos[i*3+1]*2000)+','+Math.round(pos[i*3+2]*2000);
    let a=map.get(k);if(!a){a=[];map.set(k,a);}a.push(i);}
  const out=new Float32Array(n*9);
  for(const a of map.values()){for(const i of a){const f=(i/3)|0;const l1=Math.hypot(fn[f*3],fn[f*3+1],fn[f*3+2])||1;let x=0,y=0,z=0;
      for(const j of a){const g=(j/3)|0;const l2=Math.hypot(fn[g*3],fn[g*3+1],fn[g*3+2])||1;
        const d=(fn[f*3]*fn[g*3]+fn[f*3+1]*fn[g*3+1]+fn[f*3+2]*fn[g*3+2])/(l1*l2);
        if(d>=cosT){x+=fn[g*3];y+=fn[g*3+1];z+=fn[g*3+2];}}
      const l=Math.hypot(x,y,z)||1;out[i*3]=x/l;out[i*3+1]=y/l;out[i*3+2]=z/l;}}
  return out;}
function b64ToBuf(b){const bin=atob(b);const u8=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);return u8.buffer;}
const W=cfg.width,H=cfg.height;
const gl=document.getElementById('gl');
const renderer=new THREE.WebGLRenderer({canvas:gl,antialias:true,preserveDrawingBuffer:true,alpha:false});
renderer.setPixelRatio(cfg.pixelRatio||2);renderer.setSize(W,H,false);
const scene=new THREE.Scene();scene.background=new THREE.Color(cfg.background||'#eef0f3');
let cam;
if(cfg.ortho){const hh=cfg.ortho,hw=hh*W/H;cam=new THREE.OrthographicCamera(-hw,hw,hh,-hh,0.1,4000);}
else cam=new THREE.PerspectiveCamera(cfg.fov||28,W/H,1,4000);
cam.up.set(...(cfg.up||[0,0,1]));cam.position.set(...cfg.eye);cam.lookAt(...(cfg.target||[0,0,0]));
cam.updateMatrixWorld();cam.updateProjectionMatrix();
scene.add(new THREE.HemisphereLight(0xffffff,0x8a8f99,1.05));
const view=new THREE.Vector3().subVectors(cam.position,new THREE.Vector3(...(cfg.target||[0,0,0]))).normalize();
const right=new THREE.Vector3().crossVectors(cam.up,view).normalize();const upv=new THREE.Vector3().crossVectors(view,right);
function dl(i,a,b,c){const d=new THREE.DirectionalLight(0xffffff,i);d.position.copy(view.clone().multiplyScalar(c).addScaledVector(right,a).addScaledVector(upv,b).multiplyScalar(300));scene.add(d);}
dl(1.45,-0.6,0.9,0.8);dl(0.65,0.9,0.2,0.6);dl(0.35,0.0,-0.8,0.5);
let tris=0;
for(const p of parts){
  const pos=parseSTL(b64ToBuf(p.b64));tris+=pos.length/9;
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(pos,3));
  g.setAttribute('normal',new THREE.BufferAttribute(creaseNormals(pos,p.creaseAngle||32),3));
  const col=new Float32Array(pos.length);const base=p.color,cap=p.capColor||[0.5*base[0]+0.5,0.5*base[1]+0.5,0.5*base[2]+0.5];
  const planes=cfg.capPlanes||[];const ai={x:0,y:1,z:2};
  for(let i=0;i<pos.length/9;i++){let c=base;
    for(const pl of planes){const a=ai[pl.axis];
      if(Math.abs(pos[i*9+a]-pl.value)<2e-3&&Math.abs(pos[i*9+3+a]-pl.value)<2e-3&&Math.abs(pos[i*9+6+a]-pl.value)<2e-3){c=cap;break;}}
    for(let j=0;j<3;j++){col[i*9+j*3]=c[0];col[i*9+j*3+1]=c[1];col[i*9+j*3+2]=c[2];}}
  g.setAttribute('color',new THREE.BufferAttribute(col,3));
  const op=p.opacity===undefined?1:p.opacity;
  const m=new THREE.MeshStandardMaterial({vertexColors:true,metalness:p.metalness||0.05,roughness:p.roughness||0.62,
    transparent:op<1,opacity:op,side:THREE.DoubleSide,depthWrite:op>=1,polygonOffset:true,
    polygonOffsetFactor:(op<1||p.front)?-3:1,polygonOffsetUnits:(op<1||p.front)?-3:1});
  const grp=new THREE.Group();const mesh=new THREE.Mesh(g,m);grp.add(mesh);
  if(p.edges!==false){const eg=new THREE.EdgesGeometry(g,p.edgeAngle||28);const ec=p.edgeColor||[0.05,0.05,0.06];
    const lm=new THREE.LineBasicMaterial({color:new THREE.Color(ec[0],ec[1],ec[2]),transparent:true,opacity:p.edgeOpacity===undefined?(op<1?0.55:0.85):p.edgeOpacity});
    grp.add(new THREE.LineSegments(eg,lm));}
  if(p.rotZ180About){grp.rotation.z=Math.PI;grp.position.set(2*p.rotZ180About[0],2*p.rotZ180About[1],0);}
  if(p.offset){grp.position.x+=p.offset[0];grp.position.y+=p.offset[1];grp.position.z+=p.offset[2];}
  if(op<1)mesh.renderOrder=10;
  scene.add(grp);}
renderer.render(scene,cam);
// ---- 2D overlay: title, labels with leaders
const ov=document.getElementById('ov');ov.width=W*2;ov.height=H*2;const c=ov.getContext('2d');c.scale(2,2);
const fs=cfg.fontSize||Math.round(W/62);
c.textBaseline='middle';
function proj(a){const v=new THREE.Vector3(a[0],a[1],a[2]).project(cam);return [(v.x+1)/2*W,(1-v.y)/2*H];}
if(cfg.title){c.font='600 '+Math.round(fs*1.35)+'px Helvetica, Arial, sans-serif';c.fillStyle='#14171c';c.textAlign='left';c.fillText(cfg.title,28,34+fs*0.3);}
if(cfg.subtitle){c.font=Math.round(fs*0.9)+'px Helvetica, Arial, sans-serif';c.fillStyle='#4a505a';c.textAlign='left';c.fillText(cfg.subtitle,28,34+fs*1.9);}
if(cfg.footer){c.font=Math.round(fs*0.8)+'px Helvetica, Arial, sans-serif';c.fillStyle='#4a505a';c.textAlign='left';c.fillText(cfg.footer,28,H-22);}
const labels=(cfg.labels||[]).map(l=>{const s=proj(l.anchor);return {...l,sx:s[0],sy:s[1]};});
c.font=fs+'px Helvetica, Arial, sans-serif';
const labTop=cfg.labelTop||(cfg.title?110:40),labBot=H-(cfg.labelBottom||60),lh=fs*1.5;
for(const side of ['L','R']){
  const ls=labels.filter(l=>(l.side||(l.sx<W/2?'L':'R'))===side).sort((a,b)=>a.sy-b.sy);
  if(!ls.length)continue;
  let y=labTop;for(const l of ls){l.ly=Math.max(l.sy,y);y=l.ly+lh;}
  // centre the label block on its anchors (shorter leaders, fewer crossings), then keep it on the page
  let sh=0;for(const l of ls)sh+=l.ly-l.sy;sh=Math.min(sh/ls.length,ls[0].ly-labTop);if(sh>0)for(const l of ls)l.ly-=sh;
  let over=ls[ls.length-1].ly-labBot;if(over>0){for(let i=ls.length-1;i>=0;i--){const lim=labBot-(ls.length-1-i)*lh;if(ls[i].ly>lim)ls[i].ly=lim;}}
  for(const l of ls){
    const tw=c.measureText(l.text).width;const mx=cfg.labelMargin||30;
    const tx=side==='L'?mx:W-mx;const ex=side==='L'?mx+tw+10:W-mx-tw-10;
    const kx=side==='L'?Math.min(ex+40,l.sx):Math.max(ex-40,l.sx);
    c.strokeStyle='rgba(20,23,28,0.85)';c.lineWidth=1.3;c.beginPath();c.moveTo(ex,l.ly);c.lineTo(kx,l.ly);c.lineTo(l.sx,l.sy);c.stroke();
    c.fillStyle='#14171c';c.beginPath();c.arc(l.sx,l.sy,3.2,0,6.3);c.fill();
    c.strokeStyle='rgba(238,240,243,0.95)';c.lineWidth=4;c.textAlign=side==='L'?'left':'right';c.strokeText(l.text,tx,l.ly);
    c.fillStyle='#14171c';c.fillText(l.text,tx,l.ly);}}
window.__done='tris='+tris;
`;

(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  cfg.width = cfg.width || 1600; cfg.height = cfg.height || 1200;
  const W = cfg.width, H = cfg.height;
  const parts = cfg.parts.map(p => ({ ...p, stl: undefined, b64: fs.readFileSync(p.stl).toString('base64') }));
  const html = `<!doctype html><html><body style="margin:0;background:#fff">
<div id="wrap" style="position:relative;width:${W}px;height:${H}px">
<canvas id="gl" style="position:absolute;left:0;top:0;width:${W}px;height:${H}px"></canvas>
<canvas id="ov" style="position:absolute;left:0;top:0;width:${W}px;height:${H}px"></canvas></div>
<script>${findThree()}</script>
<script>const cfg=${JSON.stringify({ ...cfg, parts: undefined })};const parts=${JSON.stringify(parts)};${PAGE_SCRIPT}</script></body></html>`;
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  let failed = false;
  page.on('pageerror', async e => { console.log('pageerror:', e.message); failed = true; await browser.close(); process.exit(1); });
  await page.setContent(html);
  await page.waitForFunction('window.__done', null, { timeout: 180000 });
  console.log(path.basename(cfg.out), await page.evaluate('window.__done'));
  await page.locator('#wrap').screenshot({ path: cfg.out });
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
