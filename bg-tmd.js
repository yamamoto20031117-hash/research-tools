/**
 * Animated 3D background — floating *real* TMD crystal fragments.
 *
 * Borrows the lattice / atom-color tables and the fracToXZ helper from
 * tmd-viewer/index.html so the geometry is identical to what that tool
 * generates: trigonal-prismatic 2H or octahedral 1T sheets with the
 * exact in-plane spacing (a) and M-X bond length (bond) from the
 * material database. Each fragment is a small 3×3 supercell of a
 * randomly picked TMD (VSe₂, MoS₂, WSe₂, NbSe₂, MoSe₂, MoTe₂, WS₂)
 * drifting and self-rotating in deep navy space.
 *
 * Drop-in: include after three.min.js and add
 *   <canvas id="bg-canvas"></canvas>
 */
(function () {
  'use strict';
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;
  if (window.matchMedia('(max-width: 600px)').matches) { canvas.style.display = 'none'; return; }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { canvas.style.display = 'none'; return; }

  // === Material database — subset of tmd-viewer DB ===
  // a in Å (in-plane), c in Å (c1T for 1T, c2H for 2H), bond = M-X in Å.
  // mCol / xCol straight from tmd-viewer MCOL_DEFAULT / XCOL_DEFAULT.
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
  // fracToXZ — identical to tmd-viewer
  function fracToXZ(f1, f2, a) { return [f1*a + f2*(-a/2), f2*(a*S3/2)]; }

  // === Build a real TMD crystal fragment ===
  function buildFragment(spec) {
    const a = spec.a;
    const r_inp = a / S3;
    const d_xm = Math.sqrt(Math.max(spec.bond*spec.bond - r_inp*r_inp, 0.1));
    const group = new THREE.Group();

    // Materials — tmd-viewer style Phong with emissive boost so they read in low-light bg
    const matM = new THREE.MeshPhongMaterial({
      color: spec.mCol, emissive: new THREE.Color(spec.mCol).multiplyScalar(0.15),
      shininess: 80, specular: 0x446688, transparent: true, opacity: 0.92,
    });
    const matX = new THREE.MeshPhongMaterial({
      color: spec.xCol, emissive: new THREE.Color(spec.xCol).multiplyScalar(0.12),
      shininess: 60, specular: 0x888844, transparent: true, opacity: 0.85,
    });
    const matBond = new THREE.MeshPhongMaterial({
      color: 0x8abbdd, transparent: true, opacity: 0.42, depthWrite: false,
    });

    const geoM = new THREE.SphereGeometry(0.45, 16, 16);
    const geoX = new THREE.SphereGeometry(0.36, 14, 14);

    const Na = 3, Nb = 3;
    const mAtoms = [], xAtoms = [];
    const yC = d_xm;  // single-layer fragment

    for (let i = -1; i <= Na; i++) {
      for (let j = -1; j <= Nb; j++) {
        if (spec.phase === '1T') {
          // Octahedral: M at (0,0), X top at (1/3,2/3), X bot at (2/3,1/3) — staggered
          const [mx, mz] = fracToXZ(i, j, a);            mAtoms.push([mx, yC, mz]);
          const [tx, tz] = fracToXZ(i+1/3, j+2/3, a);    xAtoms.push([tx, yC + d_xm, tz]);
          const [bx, bz] = fracToXZ(i+2/3, j+1/3, a);    xAtoms.push([bx, yC - d_xm, bz]);
        } else {
          // Trigonal prismatic 2H: M at (1/3,2/3), X top & bot eclipsed at (2/3,1/3)
          const [mx, mz] = fracToXZ(i+1/3, j+2/3, a);    mAtoms.push([mx, yC, mz]);
          const [xx, xz] = fracToXZ(i+2/3, j+1/3, a);
          xAtoms.push([xx, yC + d_xm, xz]);
          xAtoms.push([xx, yC - d_xm, xz]);
        }
      }
    }

    mAtoms.forEach(p => { const s = new THREE.Mesh(geoM, matM); s.position.set(p[0], p[1], p[2]); group.add(s); });
    xAtoms.forEach(p => { const s = new THREE.Mesh(geoX, matX); s.position.set(p[0], p[1], p[2]); group.add(s); });

    // M-X bonds — cylinders, only the close ones
    const bondTol = 1.15;
    const cylGeo = new THREE.CylinderGeometry(0.08, 0.08, 1, 6, 1, true);
    const up = new THREE.Vector3(0, 1, 0);
    mAtoms.forEach(m => {
      xAtoms.forEach(x => {
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

    // Re-center the group at its bounding-box centroid
    const box = new THREE.Box3().setFromObject(group);
    const center = box.getCenter(new THREE.Vector3());
    group.children.forEach(c => c.position.sub(center));
    return group;
  }

  // === Scene ===
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0a0e17, 70, 220);

  const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 500);
  camera.position.set(0, 0, 90);

  const renderer = new THREE.WebGLRenderer({
    canvas, alpha: true, antialias: true, powerPreference: 'low-power',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));

  scene.add(new THREE.AmbientLight(0x6a7a99, 0.55));
  const dirL = new THREE.DirectionalLight(0xffffff, 0.7);
  dirL.position.set(30, 50, 80);
  scene.add(dirL);
  const dirL2 = new THREE.DirectionalLight(0x88aaff, 0.3);
  dirL2.position.set(-40, -30, -60);
  scene.add(dirL2);

  // === Spawn fragments — one per random TMD ===
  const FRAGMENT_COUNT = 4;
  const fragments = [];
  for (let i = 0; i < FRAGMENT_COUNT; i++) {
    const spec = TMD[Math.floor(Math.random() * TMD.length)];
    const f = buildFragment(spec);
    f.position.set(
      (Math.random() - 0.5) * 180,
      (Math.random() - 0.5) * 110,
      (Math.random() - 0.5) * 100 - 30
    );
    f.rotation.set(
      Math.random() * Math.PI * 2,
      Math.random() * Math.PI * 2,
      Math.random() * Math.PI * 2,
    );
    f.scale.setScalar(0.7 + Math.random() * 0.6);
    f.userData = {
      rotSpeed: new THREE.Vector3(
        (Math.random() - 0.5) * 0.0015,
        (Math.random() - 0.5) * 0.0020,
        (Math.random() - 0.5) * 0.0010,
      ),
      driftSpeed: new THREE.Vector3(
        (Math.random() - 0.5) * 0.035,
        (Math.random() - 0.5) * 0.035,
        0.015 + Math.random() * 0.035,
      ),
    };
    scene.add(f);
    fragments.push(f);
  }

  // === Ambient star field for depth ===
  const STAR_COUNT = 200;
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(STAR_COUNT * 3);
  for (let i = 0; i < STAR_COUNT; i++) {
    starPos[i*3]     = (Math.random() - 0.5) * 320;
    starPos[i*3 + 1] = (Math.random() - 0.5) * 200;
    starPos[i*3 + 2] = (Math.random() - 0.5) * 240 - 40;
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({
    color: 0x9ad0ff, size: 0.4, transparent: true, opacity: 0.55, sizeAttenuation: true,
  })));

  // === Mouse parallax ===
  let mouseX = 0, mouseY = 0, targetX = 0, targetY = 0;
  window.addEventListener('mousemove', e => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  function onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  window.addEventListener('resize', onResize);
  onResize();

  // === Animate ===
  let prev = performance.now();
  function animate(now) {
    requestAnimationFrame(animate);
    const dt = (now - prev) / 1000;
    prev = now;

    targetX += (mouseX - targetX) * 0.045;
    targetY += (mouseY - targetY) * 0.045;

    camera.position.x = targetX * 8;
    camera.position.y = -targetY * 5;
    camera.position.z = 90 + Math.sin(now * 0.00018) * 10;
    camera.lookAt(0, 0, 0);

    for (const f of fragments) {
      f.rotation.x += f.userData.rotSpeed.x;
      f.rotation.y += f.userData.rotSpeed.y;
      f.rotation.z += f.userData.rotSpeed.z;
      f.position.x += f.userData.driftSpeed.x * dt * 60;
      f.position.y += f.userData.driftSpeed.y * dt * 60;
      f.position.z += f.userData.driftSpeed.z * dt * 60;
      // Respawn when drifting out of bounds
      if (f.position.length() > 160) {
        f.position.set(
          (Math.random() - 0.5) * 180,
          (Math.random() - 0.5) * 110,
          -90 - Math.random() * 20,
        );
        f.scale.setScalar(0.7 + Math.random() * 0.6);
      }
    }

    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
