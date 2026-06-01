/**
 * Animated 3D background — "museum exhibit" style.
 *
 * One large stacked TMD slab sits at the origin. The camera slowly
 * orbits it on a tilted circular path and breathes in/out with a sine
 * dolly. Mouse adds a gentle tilt. Atoms themselves are static so the
 * lattice reads clearly behind the UI — no chaotic drift, no random
 * flying fragments. Picks a TMD material every page load so the
 * crystal cycles between VSe₂, MoS₂, WSe₂ etc.
 *
 * Lattice geometry mirrors tmd-viewer/index.html exactly (DB rows,
 * fracToXZ, 1T vs 2H rules, d_xm = √(bond² − (a/√3)²)).
 *
 * Drop-in: add <canvas id="bg-canvas"></canvas> and load after three.min.js.
 */
(function () {
  'use strict';
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;
  if (window.matchMedia('(max-width: 600px)').matches) { canvas.style.display = 'none'; return; }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { canvas.style.display = 'none'; return; }

  // === TMD material table (subset of tmd-viewer DB) ===
  const TMD = [
    { name:'VSe₂',  m:'V',  x:'Se', phase:'1T', a:3.354, c:6.10,  bond:2.50, mCol:0x2e8bc0, xCol:0xd48a00 },
    { name:'TiSe₂', m:'Ti', x:'Se', phase:'1T', a:3.540, c:6.01,  bond:2.55, mCol:0x7799aa, xCol:0xd48a00 },
    { name:'TaS₂',  m:'Ta', x:'S',  phase:'1T', a:3.367, c:5.90,  bond:2.48, mCol:0x667788, xCol:0xddc000 },
    { name:'MoS₂',  m:'Mo', x:'S',  phase:'2H', a:3.160, c:6.15,  bond:2.41, mCol:0x8855bb, xCol:0xddc000 },
    { name:'MoSe₂', m:'Mo', x:'Se', phase:'2H', a:3.289, c:6.47,  bond:2.53, mCol:0x8855bb, xCol:0xd48a00 },
    { name:'WS₂',   m:'W',  x:'S',  phase:'2H', a:3.153, c:6.16,  bond:2.42, mCol:0x4466aa, xCol:0xddc000 },
    { name:'WSe₂',  m:'W',  x:'Se', phase:'2H', a:3.282, c:6.48,  bond:2.53, mCol:0x4466aa, xCol:0xd48a00 },
    { name:'NbSe₂', m:'Nb', x:'Se', phase:'2H', a:3.442, c:6.27,  bond:2.60, mCol:0x22aa88, xCol:0xd48a00 },
  ];

  const S3 = Math.sqrt(3);
  // Identical to tmd-viewer
  function fracToXZ(f1, f2, a) { return [f1*a + f2*(-a/2), f2*(a*S3/2)]; }

  // === Build a multi-layer TMD crystal at origin ===
  function buildSlab(spec, Na, Nb, layers) {
    const a = spec.a;
    const r_inp = a / S3;
    const d_xm = Math.sqrt(Math.max(spec.bond*spec.bond - r_inp*r_inp, 0.1));
    const layerStep = spec.c;   // c_layer between sheets
    const group = new THREE.Group();

    const matM = new THREE.MeshPhongMaterial({
      color: spec.mCol, emissive: new THREE.Color(spec.mCol).multiplyScalar(0.12),
      shininess: 80, specular: 0x446688, transparent: true, opacity: 0.92,
    });
    const matX = new THREE.MeshPhongMaterial({
      color: spec.xCol, emissive: new THREE.Color(spec.xCol).multiplyScalar(0.10),
      shininess: 60, specular: 0x888844, transparent: true, opacity: 0.86,
    });
    const matBond = new THREE.MeshPhongMaterial({
      color: 0x8abbdd, transparent: true, opacity: 0.4, depthWrite: false,
    });

    const geoM = new THREE.SphereGeometry(0.5, 18, 18);
    const geoX = new THREE.SphereGeometry(0.40, 14, 14);
    const cylGeo = new THREE.CylinderGeometry(0.085, 0.085, 1, 6, 1, true);
    const up = new THREE.Vector3(0, 1, 0);

    const mAll = [], xAll = [];

    for (let l = 0; l < layers; l++) {
      const yC = (l - (layers - 1) / 2) * layerStep;
      for (let i = -Na; i <= Na; i++) {
        for (let j = -Nb; j <= Nb; j++) {
          if (spec.phase === '1T') {
            const [mx, mz] = fracToXZ(i, j, a);            mAll.push([mx, yC, mz, l]);
            const [tx, tz] = fracToXZ(i+1/3, j+2/3, a);    xAll.push([tx, yC + d_xm, tz, l]);
            const [bx, bz] = fracToXZ(i+2/3, j+1/3, a);    xAll.push([bx, yC - d_xm, bz, l]);
          } else {
            const [mx, mz] = fracToXZ(i+1/3, j+2/3, a);    mAll.push([mx, yC, mz, l]);
            const [xx, xz] = fracToXZ(i+2/3, j+1/3, a);
            xAll.push([xx, yC + d_xm, xz, l]);
            xAll.push([xx, yC - d_xm, xz, l]);
          }
        }
      }
    }

    // Render atoms
    mAll.forEach(p => { const s = new THREE.Mesh(geoM, matM); s.position.set(p[0], p[1], p[2]); group.add(s); });
    xAll.forEach(p => { const s = new THREE.Mesh(geoX, matX); s.position.set(p[0], p[1], p[2]); group.add(s); });

    // M-X bonds within each layer only (don't draw inter-layer bonds)
    const bondTol = 1.15;
    const mByLayer = {}, xByLayer = {};
    mAll.forEach(p => { (mByLayer[p[3]] = mByLayer[p[3]] || []).push(p); });
    xAll.forEach(p => { (xByLayer[p[3]] = xByLayer[p[3]] || []).push(p); });
    for (let l = 0; l < layers; l++) {
      const Ms = mByLayer[l] || [], Xs = xByLayer[l] || [];
      Ms.forEach(m => {
        Xs.forEach(x => {
          const dx = m[0]-x[0], dy = m[1]-x[1], dz = m[2]-x[2];
          const len = Math.sqrt(dx*dx + dy*dy + dz*dz);
          if (len < spec.bond * bondTol) {
            const cyl = new THREE.Mesh(cylGeo, matBond);
            cyl.position.set((m[0]+x[0])/2, (m[1]+x[1])/2, (m[2]+x[2])/2);
            const dir = new THREE.Vector3(x[0]-m[0], x[1]-m[1], x[2]-m[2]).normalize();
            cyl.quaternion.setFromUnitVectors(up, dir);
            cyl.scale.y = len;
            group.add(cyl);
          }
        });
      });
    }

    // Re-center
    const box = new THREE.Box3().setFromObject(group);
    const center = box.getCenter(new THREE.Vector3());
    group.children.forEach(c => c.position.sub(center));
    return group;
  }

  // === Scene ===
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0a0e17, 30, 130);

  const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 500);

  const renderer = new THREE.WebGLRenderer({
    canvas, alpha: true, antialias: true, powerPreference: 'low-power',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));

  // Lighting — rim light for material edges
  scene.add(new THREE.AmbientLight(0x556677, 0.55));
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.85);
  keyLight.position.set(40, 60, 50);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0x88aaff, 0.45);
  rimLight.position.set(-50, -20, -40);
  scene.add(rimLight);

  // === Pick a TMD and build the slab ===
  const spec = TMD[Math.floor(Math.random() * TMD.length)];
  // 5×5×4 layers — enough to fill the frame at the camera distance
  const slab = buildSlab(spec, 4, 4, 4);
  scene.add(slab);

  // Slight initial tilt so layers face the camera nicely
  slab.rotation.x = 0.45;
  slab.rotation.z = 0.15;

  // === Ambient particles around the slab for atmosphere ===
  const STAR_COUNT = 300;
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(STAR_COUNT * 3);
  for (let i = 0; i < STAR_COUNT; i++) {
    // Sphere shell around origin, radius 50-120
    const r = 50 + Math.random() * 70;
    const t = Math.random() * Math.PI * 2;
    const p = Math.acos(2 * Math.random() - 1);
    starPos[i*3]     = r * Math.sin(p) * Math.cos(t);
    starPos[i*3 + 1] = r * Math.cos(p);
    starPos[i*3 + 2] = r * Math.sin(p) * Math.sin(t);
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({
    color: 0x9ad0ff, size: 0.45, transparent: true, opacity: 0.55, sizeAttenuation: true,
  }));
  scene.add(stars);

  function onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  window.addEventListener('resize', onResize);
  onResize();

  // === Animate: camera orbit, slab static, no mouse input ===
  // Tilted circular orbit at 36 unit radius, completes one revolution
  // in 90 s. Sinusoidal dolly: ±5 units in/out every 25 s. The camera
  // always looks at the slab center.
  const ORBIT_RADIUS = 36;
  const ORBIT_PERIOD_S = 90;
  const DOLLY_AMPL = 5;
  const DOLLY_PERIOD_S = 25;

  function animate(now) {
    requestAnimationFrame(animate);

    const t = now * 0.001;
    const orbitT = (t / ORBIT_PERIOD_S) * Math.PI * 2;
    const dolly = Math.sin((t / DOLLY_PERIOD_S) * Math.PI * 2) * DOLLY_AMPL;
    const r = ORBIT_RADIUS + dolly;

    camera.position.x = r * Math.cos(orbitT);
    camera.position.y = 12 + r * 0.18 * Math.sin(orbitT * 0.6);
    camera.position.z = r * Math.sin(orbitT);
    camera.lookAt(0, 0, 0);

    // Stars rotate very slowly to give a tiny life signal
    stars.rotation.y += 0.0003;

    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
