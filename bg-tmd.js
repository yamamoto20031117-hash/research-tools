/**
 * Animated 3D background — floating TMD lattice fragments.
 *
 * Uses Three.js (already loaded by tmd-viewer at the same CDN version).
 * Hexagonal MX2 patches with M (metal, blue) and X (chalcogen, amber) atoms,
 * connected by faint cyan wireframe bonds, slowly rotating and drifting
 * across a deep navy void.
 *
 * Lightweight: ~3 fragments × ~30 atoms each + 1 line-segment per fragment.
 * Camera does a slow sinusoidal dolly + mouse parallax for depth.
 *
 * Drop-in: include after three.min.js and add <canvas id="bg-canvas"></canvas>.
 */
(function () {
  'use strict';
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  // Skip on tiny screens / mobile — saves battery and the absent parallax doesn't shine on touch anyway.
  const mql = window.matchMedia('(max-width: 600px)');
  if (mql.matches) { canvas.style.display = 'none'; return; }

  // Respect user preference
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    canvas.style.display = 'none';
    return;
  }

  // ===== Scene setup =====
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0a0e17, 80, 220);

  const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 500);
  camera.position.set(0, 0, 110);

  const renderer = new THREE.WebGLRenderer({
    canvas, alpha: true, antialias: true, powerPreference: 'low-power'
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));

  // Lights
  scene.add(new THREE.AmbientLight(0x6a7a99, 0.55));
  const dir = new THREE.DirectionalLight(0xffffff, 0.65);
  dir.position.set(30, 50, 80);
  scene.add(dir);
  const dirBack = new THREE.DirectionalLight(0x88aaff, 0.25);
  dirBack.position.set(-40, -30, -60);
  scene.add(dirBack);

  // ===== Build one TMD-like hexagonal fragment =====
  const A = 5.5;     // lattice spacing (scene units)
  const PATCH = 3;   // 3 → ~50 atoms per fragment (small enough)

  function buildFragment() {
    const group = new THREE.Group();
    const mPositions = [];

    // Honeycomb lattice (triangular Bravais with 2 basis points → metal sites)
    for (let i = -PATCH; i <= PATCH; i++) {
      for (let j = -PATCH; j <= PATCH; j++) {
        if (Math.abs(i + j) > PATCH) continue;  // hexagonal patch boundary
        const x = A * (i + j * 0.5);
        const z = A * j * Math.sqrt(3) / 2;
        mPositions.push([x, 0, z]);
      }
    }

    // M atoms — blue/violet metal (V/Mo-like)
    const mGeom = new THREE.SphereGeometry(0.7, 14, 14);
    const mMat = new THREE.MeshStandardMaterial({
      color: 0xa6b0d8, emissive: 0x1a2440,
      metalness: 0.55, roughness: 0.35,
      transparent: true, opacity: 0.82,
    });
    mPositions.forEach(p => {
      const m = new THREE.Mesh(mGeom, mMat);
      m.position.set(p[0], 0, p[2]);
      group.add(m);
    });

    // X atoms (chalcogen) — amber, slightly above/below in 2H trigonal prism
    const xGeom = new THREE.SphereGeometry(0.45, 12, 12);
    const xMat = new THREE.MeshStandardMaterial({
      color: 0xf5b94a, emissive: 0x4a2a08,
      metalness: 0.2, roughness: 0.6,
      transparent: true, opacity: 0.7,
    });
    mPositions.forEach(p => {
      // Two X atoms — above and below — at hollow site
      const xOff = A * 0.5774 / 2;  // 1/(2√3) of lattice spacing
      const positions = [
        [p[0] + xOff, 1.4, p[2] + xOff * 0.577],
        [p[0] + xOff, -1.4, p[2] + xOff * 0.577],
      ];
      positions.forEach(xp => {
        const m = new THREE.Mesh(xGeom, xMat);
        m.position.set(xp[0], xp[1], xp[2]);
        group.add(m);
      });
    });

    // Bond wireframe — M-M nearest neighbor lines (cyan, low opacity)
    const bondPos = [];
    for (let i = 0; i < mPositions.length; i++) {
      const [x1, , z1] = mPositions[i];
      for (let j = i + 1; j < mPositions.length; j++) {
        const [x2, , z2] = mPositions[j];
        const dx = x1 - x2, dz = z1 - z2;
        if (Math.sqrt(dx * dx + dz * dz) < A * 1.05) {
          bondPos.push(x1, 0, z1, x2, 0, z2);
        }
      }
    }
    const bondGeom = new THREE.BufferGeometry();
    bondGeom.setAttribute('position', new THREE.Float32BufferAttribute(bondPos, 3));
    const bondMat = new THREE.LineBasicMaterial({
      color: 0x58a6ff, transparent: true, opacity: 0.4, depthWrite: false,
    });
    group.add(new THREE.LineSegments(bondGeom, bondMat));

    return group;
  }

  // ===== Spawn a handful of fragments randomly placed =====
  const FRAGMENT_COUNT = 4;
  const fragments = [];
  for (let i = 0; i < FRAGMENT_COUNT; i++) {
    const f = buildFragment();
    f.position.set(
      (Math.random() - 0.5) * 200,
      (Math.random() - 0.5) * 120,
      (Math.random() - 0.5) * 120 - 30
    );
    f.rotation.set(
      Math.random() * Math.PI * 2,
      Math.random() * Math.PI * 2,
      Math.random() * Math.PI * 2,
    );
    const s = 0.6 + Math.random() * 0.7;
    f.scale.setScalar(s);
    f.userData = {
      rotSpeed: new THREE.Vector3(
        (Math.random() - 0.5) * 0.0018,
        (Math.random() - 0.5) * 0.0022,
        (Math.random() - 0.5) * 0.0012,
      ),
      driftSpeed: new THREE.Vector3(
        (Math.random() - 0.5) * 0.04,
        (Math.random() - 0.5) * 0.04,
        0.02 + Math.random() * 0.04,
      ),
    };
    scene.add(f);
    fragments.push(f);
  }

  // ===== Floating point-cloud — ambient depth =====
  const STAR_COUNT = 240;
  const starGeom = new THREE.BufferGeometry();
  const starPos = new Float32Array(STAR_COUNT * 3);
  for (let i = 0; i < STAR_COUNT; i++) {
    starPos[i*3]     = (Math.random() - 0.5) * 320;
    starPos[i*3 + 1] = (Math.random() - 0.5) * 200;
    starPos[i*3 + 2] = (Math.random() - 0.5) * 250 - 50;
  }
  starGeom.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
  const starMat = new THREE.PointsMaterial({
    color: 0x9ad0ff, size: 0.4, transparent: true, opacity: 0.55, sizeAttenuation: true,
  });
  scene.add(new THREE.Points(starGeom, starMat));

  // ===== Mouse parallax =====
  let mouseX = 0, mouseY = 0;
  let targetX = 0, targetY = 0;
  window.addEventListener('mousemove', e => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  // ===== Resize =====
  function onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  window.addEventListener('resize', onResize);
  onResize();

  // ===== Animate =====
  let prev = performance.now();
  function animate(now) {
    requestAnimationFrame(animate);
    const dt = (now - prev) / 1000;
    prev = now;

    targetX += (mouseX - targetX) * 0.045;
    targetY += (mouseY - targetY) * 0.045;

    camera.position.x = targetX * 9;
    camera.position.y = -targetY * 6;
    camera.position.z = 110 + Math.sin(now * 0.00015) * 12;
    camera.lookAt(0, 0, 0);

    for (const f of fragments) {
      f.rotation.x += f.userData.rotSpeed.x;
      f.rotation.y += f.userData.rotSpeed.y;
      f.rotation.z += f.userData.rotSpeed.z;
      f.position.x += f.userData.driftSpeed.x * dt * 60;
      f.position.y += f.userData.driftSpeed.y * dt * 60;
      f.position.z += f.userData.driftSpeed.z * dt * 60;
      // Wrap around when too far
      if (f.position.length() > 170) {
        f.position.set(
          (Math.random() - 0.5) * 200,
          (Math.random() - 0.5) * 120,
          -100 - Math.random() * 20,
        );
        const s = 0.6 + Math.random() * 0.7;
        f.scale.setScalar(s);
      }
    }

    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
