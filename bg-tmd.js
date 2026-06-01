/**
 * Animated 3D background — VSe₂ host + DBPO helicene intercalant.
 *
 * Two layers of 1T-VSe₂ with an expanded c-axis gap, and a single
 * DBPO P-helicene molecule (C40H22N2O2, 66 atoms from CCDC 1040766,
 * H stripped for cleaner read) sitting in the gap. Mirrors the actual
 * intercalation target of the user's research. The whole scene is
 * static — only the camera moves on a slow tilted orbit + sinusoidal
 * dolly so the structure stays legible while quietly rotating in view.
 *
 * VSe₂ geometry is identical to tmd-viewer/index.html (fracToXZ, 1T
 * rules, d_xm = √(bond² − (a/√3)²)). Helicene atom positions are the
 * raw P-enantiomer Cartesians extracted from the CCDC CIF, centered
 * at the molecular centroid.
 *
 * Drop-in: load after three.min.js, add <canvas id="bg-canvas"></canvas>.
 */
(function () {
  'use strict';
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;
  if (window.matchMedia('(max-width: 600px)').matches) { canvas.style.display = 'none'; return; }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { canvas.style.display = 'none'; return; }

  // === Host material: 1T-VSe₂ (from tmd-viewer DB) ===
  const VSE2 = { m:'V', x:'Se', phase:'1T', a:3.354, c:6.10, bond:2.50, mCol:0x2e8bc0, xCol:0xd48a00 };

  const S3 = Math.sqrt(3);
  function fracToXZ(f1, f2, a) { return [f1*a + f2*(-a/2), f2*(a*S3/2)]; }

  // === Build a VSe₂ slab with custom inter-layer spacing ===
  function buildSlab(spec, Na, Nb, layers, layerStep) {
    const a = spec.a;
    const r_inp = a / S3;
    const d_xm = Math.sqrt(Math.max(spec.bond*spec.bond - r_inp*r_inp, 0.1));
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

    const geoM = new THREE.SphereGeometry(0.55, 18, 18);
    const geoX = new THREE.SphereGeometry(0.42, 14, 14);
    const cylGeo = new THREE.CylinderGeometry(0.085, 0.085, 1, 6, 1, true);
    const up = new THREE.Vector3(0, 1, 0);

    const mByLayer = [], xByLayer = [];
    for (let l = 0; l < layers; l++) {
      mByLayer.push([]);
      xByLayer.push([]);
      const yC = (l - (layers - 1) / 2) * layerStep;
      for (let i = -Na; i <= Na; i++) {
        for (let j = -Nb; j <= Nb; j++) {
          const [mx, mz] = fracToXZ(i, j, a);            mByLayer[l].push([mx, yC, mz]);
          const [tx, tz] = fracToXZ(i+1/3, j+2/3, a);    xByLayer[l].push([tx, yC + d_xm, tz]);
          const [bx, bz] = fracToXZ(i+2/3, j+1/3, a);    xByLayer[l].push([bx, yC - d_xm, bz]);
        }
      }
    }
    mByLayer.forEach(arr => arr.forEach(p => { const s = new THREE.Mesh(geoM, matM); s.position.set(p[0], p[1], p[2]); group.add(s); }));
    xByLayer.forEach(arr => arr.forEach(p => { const s = new THREE.Mesh(geoX, matX); s.position.set(p[0], p[1], p[2]); group.add(s); }));

    const bondTol = 1.15;
    for (let l = 0; l < layers; l++) {
      const Ms = mByLayer[l], Xs = xByLayer[l];
      Ms.forEach(m => {
        Xs.forEach(x => {
          const dx = m[0]-x[0], dy = m[1]-x[1], dz = m[2]-x[2];
          const len = Math.sqrt(dx*dx + dy*dy + dz*dz);
          if (len < spec.bond * bondTol) {
            const cyl = new THREE.Mesh(cylGeo, matBond);
            cyl.position.set((m[0]+x[0])/2, (m[1]+x[1])/2, (m[2]+x[2])/2);
            cyl.quaternion.setFromUnitVectors(up, new THREE.Vector3(x[0]-m[0], x[1]-m[1], x[2]-m[2]).normalize());
            cyl.scale.y = len;
            group.add(cyl);
          }
        });
      });
    }
    return group;
  }

  // === DBPO P-helicene Cartesian coords (Å) — from CCDC 1040766 ===
  // [element, x, y, z]. H atoms included but skipped at render time.
  const HELICENE = [
    ['H', 4.166, -3.401, 1.403], ['H', 4.061, -5.258, 3.059],
    ['H', 3.325,  8.116, 3.687], ['H', 1.890,  6.848, 2.226],
    ['H', 1.344,  7.691, 0.064], ['H', 1.390,  9.514,-1.570],
    ['H', 2.607, -3.384,-5.062], ['H', 3.598, -2.345, 7.858],
    ['H',-6.467, -0.610, 8.924], ['H',-5.305,  0.903,-4.676],
    ['H',-5.229,  0.595,-2.360], ['H',-3.943, -1.793,-1.714],
    ['H',-1.734, -2.190,-2.764], ['H', 0.524, -1.593,-3.066],
    ['H', 1.457,  0.190,-1.879], ['H', 0.171,  1.470,-0.364],
    ['H',-2.041,  1.735, 0.870], ['H',-5.366,  1.481, 3.923],
    ['H', 4.305,  1.332, 3.698], ['H', 2.143,  0.586, 4.381],
    ['H', 0.843, -0.862, 2.949], ['H', 1.755, -1.701, 0.962],
    ['C', 3.239, -3.420,-0.431], ['C', 3.584, -3.929, 0.790],
    ['C', 3.139, -5.217, 1.188], ['C', 3.476, -5.766, 2.453],
    ['C', 3.022,  8.457, 2.823], ['C', 2.213,  7.710, 1.948],
    ['C', 1.883,  8.196, 0.713], ['C', 2.332,  9.475, 0.301],
    ['C', 2.011, -5.446,-0.969], ['C', 2.454, -4.210,-1.317],
    ['C', 3.048, -2.874,-3.154], ['C', 3.171, -2.827,-4.504],
    ['C', 4.057, -1.886,-5.091], ['C', 4.129, -1.730,-6.501],
    ['C',-6.499, -0.739,-5.110], ['C',-5.779,  0.152,-4.281],
    ['C',-5.766, -0.010,-2.919], ['C',-6.515, -1.050,-2.305],
    ['C',-6.544, -1.280,-0.894], ['C', 3.856, -2.081,-2.310],
    ['C',-4.277, -0.434,-0.207], ['C',-3.513, -1.100,-1.133],
    ['C',-2.150, -0.755,-1.343], ['C',-1.334, -1.450,-2.269],
    ['C',-0.017, -1.095,-2.444], ['C', 0.533, -0.025,-1.742],
    ['C',-0.228,  0.696,-0.860], ['C',-1.592,  0.346,-0.620],
    ['C',-2.390,  0.995, 0.342], ['C',-3.662,  0.575, 0.583],
    ['C',-5.450,  0.531, 2.121], ['C',-5.875,  0.832, 3.380],
    ['C', 4.299,  0.275, 1.903], ['C', 3.733,  0.703, 3.132],
    ['C', 2.489,  0.282, 3.518], ['C', 1.751, -0.595, 2.689],
    ['C', 2.294, -1.088, 1.529], ['C', 3.583, -0.679, 1.105],
    ['C', 4.182, -1.113,-0.122], ['C',-6.120, -0.429, 1.329],
    ['N', 3.628, -2.148,-0.922], ['N',-5.655, -0.643, 0.014],
    ['O', 2.121, -3.725,-2.576], ['O',-4.351,  1.195, 1.615],
  ];

  // === Build helicene mesh group (H atoms hidden) ===
  function buildHelicene() {
    const group = new THREE.Group();
    const pts = HELICENE.filter(p => p[0] !== 'H');
    // Center at centroid
    let cx = 0, cy = 0, cz = 0;
    pts.forEach(p => { cx += p[1]; cy += p[2]; cz += p[3]; });
    cx /= pts.length; cy /= pts.length; cz /= pts.length;

    const colors = { C: 0xa8b0bd, N: 0x4060ee, O: 0xee3030 };
    const radii  = { C: 0.32,     N: 0.34,     O: 0.30 };
    const mats   = {}, geos = {};
    for (const k in colors) {
      mats[k] = new THREE.MeshPhongMaterial({
        color: colors[k], emissive: new THREE.Color(colors[k]).multiplyScalar(0.15),
        shininess: 70, transparent: true, opacity: 0.94,
      });
      geos[k] = new THREE.SphereGeometry(radii[k], 14, 14);
    }

    pts.forEach(([e, x, y, z]) => {
      const m = new THREE.Mesh(geos[e], mats[e]);
      m.position.set(x - cx, y - cy, z - cz);
      group.add(m);
    });

    // Covalent bonds: any pair with d < 1.65 Å
    const cylGeo = new THREE.CylinderGeometry(0.06, 0.06, 1, 6, 1, true);
    const bondMat = new THREE.MeshPhongMaterial({
      color: 0xb6c2d4, transparent: true, opacity: 0.62, depthWrite: false,
    });
    const up = new THREE.Vector3(0, 1, 0);
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const [e1, x1, y1, z1] = pts[i];
        const [e2, x2, y2, z2] = pts[j];
        const dx = x1 - x2, dy = y1 - y2, dz = z1 - z2;
        const d = Math.sqrt(dx*dx + dy*dy + dz*dz);
        if (d < 1.65) {
          const cyl = new THREE.Mesh(cylGeo, bondMat);
          cyl.position.set((x1+x2)/2 - cx, (y1+y2)/2 - cy, (z1+z2)/2 - cz);
          cyl.quaternion.setFromUnitVectors(up, new THREE.Vector3(x2-x1, y2-y1, z2-z1).normalize());
          cyl.scale.y = d;
          group.add(cyl);
        }
      }
    }
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

  scene.add(new THREE.AmbientLight(0x556677, 0.55));
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.85);
  keyLight.position.set(40, 60, 50);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0x88aaff, 0.45);
  rimLight.position.set(-50, -20, -40);
  scene.add(rimLight);

  // === Compose the scene: VSe₂ slab + helicene in the gap ===
  // 2 layers separated by 16 Å (vs natural 6.10 Å) — enough vdW space for DBPO.
  const INTERCALATED_GAP = 16;
  const slab = buildSlab(VSE2, 4, 4, 2, INTERCALATED_GAP);
  scene.add(slab);

  const helicene = buildHelicene();
  helicene.position.set(0, 0, 0);   // sits in the middle of the slab gap
  scene.add(helicene);

  // Mild tilt — user reported the old 0.45 was too steep.
  const sceneRoot = new THREE.Group();
  sceneRoot.add(slab);
  sceneRoot.add(helicene);
  sceneRoot.rotation.x = 0.18;
  sceneRoot.rotation.z = 0.04;
  scene.add(sceneRoot);

  // === Ambient stars for depth ===
  const STAR_COUNT = 280;
  const starGeo = new THREE.BufferGeometry();
  const starPos = new Float32Array(STAR_COUNT * 3);
  for (let i = 0; i < STAR_COUNT; i++) {
    const r = 55 + Math.random() * 65;
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

  // === Animate: tilted camera orbit, scene static ===
  const ORBIT_RADIUS = 38;
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

    stars.rotation.y += 0.0003;
    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
