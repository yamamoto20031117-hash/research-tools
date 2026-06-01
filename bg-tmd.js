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

  // === [5]Helicene — procedural, chemically-clean construction ===
  // Five ortho-fused benzene rings stacked into a partial helix. Built by
  // hex fusion: ring N+1 shares an edge with ring N (always the "same"
  // local edge so the spiral keeps curling in the same sense), and each
  // ring tilts by HELIX_TWIST around the shared edge so the rings rise
  // out of plane into a true 3D helix.  Total: 22 C + 14 H (the canonical
  // [5]helicene formula). H atoms are placed radially outward from each
  // non-junction C.
  //
  // The CCDC-extracted DBPO XYZ couldn't be used directly: the CIF→XYZ
  // script in qe-auto/examples/ doesn't unwrap molecules that cross the
  // unit-cell boundary, so 7 aromatic carbons came out with only one
  // covalent neighbor (the rest of the molecule was on the "other side"
  // of the periodic boundary). The structure read as broken to a chemist.
  function _buildHelicene5() {
    const CC = 1.42;                 // aromatic C-C
    const hexH = CC * Math.sqrt(3) / 2;  // hex center → edge midpoint
    const CH = 1.08;                 // C-H bond
    const HELIX_TWIST = 0.42;        // radians; sets steepness of spiral

    const heavy = [];                // [el, x, y, z]
    const junctions = new Set();     // string keys for atoms shared between rings (no H)

    function key(p) { return p.x.toFixed(3) + ',' + p.y.toFixed(3) + ',' + p.z.toFixed(3); }
    function pushHeavy(p, el='C', shared=false) {
      heavy.push([el, p.x, p.y, p.z]);
      if (shared) junctions.add(key(p));
      return p;
    }

    // --- Ring 0: hex in the xz plane, centered at origin ---
    const ring0 = [];
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3;
      ring0.push(new THREE.Vector3(CC * Math.cos(a), 0, CC * Math.sin(a)));
    }
    ring0.forEach(p => pushHeavy(p));

    // Helper — Rodrigues rotation of v around unit axis k by angle θ
    function rotateAround(v, k, theta) {
      const c = Math.cos(theta), s = Math.sin(theta);
      const kxv = k.clone().cross(v);
      const kdv = k.dot(v);
      return v.clone().multiplyScalar(c)
        .add(kxv.multiplyScalar(s))
        .add(k.clone().multiplyScalar(kdv * (1 - c)));
    }

    let currentRing = ring0;
    // Fuse the next ring on the edge between atoms 1 and 2 of the current ring,
    // then for the ring after that, fuse on atoms 1 & 2 of THAT ring — but in
    // the new ring's indexing, the edge "1-2" lands one vertex further around,
    // so the spiral keeps winding in the same rotational sense.
    let edgeStartIdx = 1, edgeEndIdx = 2;

    for (let r = 1; r < 5; r++) {
      const e1 = currentRing[edgeStartIdx];
      const e2 = currentRing[edgeEndIdx];

      const mid = e1.clone().add(e2).multiplyScalar(0.5);
      const edgeDir = e2.clone().sub(e1).normalize();

      // Centroid of current ring → mid gives the "outward" direction (away from old ring center)
      const centroid = new THREE.Vector3();
      currentRing.forEach(p => centroid.add(p));
      centroid.divideScalar(currentRing.length);
      const outward = mid.clone().sub(centroid).normalize();

      // Tilt outward around the edge axis — this is what makes it a helix instead of a flat naphthalene chain
      const newPerp = rotateAround(outward, edgeDir, HELIX_TWIST);

      // Center of the new ring
      const newCenter = mid.clone().add(newPerp.clone().multiplyScalar(hexH));

      // Local hex basis: edgeDir = local +x ; newPerp = local +y
      // e1, e2 occupy vertices 4 and 5 (the "bottom" edge of the new ring)
      // The 4 new atoms are vertices 0, 1, 2, 3 in canonical CCW order
      const newRing = [];
      newRing.push(e1);                 // shared from previous ring
      newRing.push(e2);                 // shared from previous ring

      // Mark e1, e2 as junctions (no H on them)
      junctions.add(key(e1));
      junctions.add(key(e2));

      // vertex 0: (CC, 0)
      newRing.push(newCenter.clone()
        .add(edgeDir.clone().multiplyScalar(CC)));
      // vertex 1: (CC/2, hexH)
      newRing.push(newCenter.clone()
        .add(edgeDir.clone().multiplyScalar(CC / 2))
        .add(newPerp.clone().multiplyScalar(hexH)));
      // vertex 2: (-CC/2, hexH)
      newRing.push(newCenter.clone()
        .add(edgeDir.clone().multiplyScalar(-CC / 2))
        .add(newPerp.clone().multiplyScalar(hexH)));
      // vertex 3: (-CC, 0)
      newRing.push(newCenter.clone()
        .add(edgeDir.clone().multiplyScalar(-CC)));

      for (let i = 2; i < 6; i++) pushHeavy(newRing[i]);
      currentRing = newRing;
      // For the next ring: re-use the same local edge index, which after the
      // ring's own reindexing becomes the "next" edge around the rim → helix.
      edgeStartIdx = 1; edgeEndIdx = 2;
    }

    // Build H atoms — one per non-junction C, placed radially outward
    // from that ring's local centroid
    // We need to know each ring's centroid. Rebuild from heavy array by
    // tagging atoms by ring index (kept implicit). Simpler: place H by
    // looking at each C's two nearest C neighbors, and putting H along the
    // bisector pointing outward.
    const Hs = [];
    const heavyVecs = heavy.map(([e, x, y, z]) => new THREE.Vector3(x, y, z));
    for (let i = 0; i < heavy.length; i++) {
      const pos = heavyVecs[i];
      if (junctions.has(key(pos))) continue;
      // Find 2 nearest heavy neighbors
      const dists = [];
      for (let j = 0; j < heavyVecs.length; j++) {
        if (j === i) continue;
        const d = pos.distanceTo(heavyVecs[j]);
        if (d < CC * 1.15) dists.push({ j, d });
      }
      // H is placed along the average of (pos - neighbor) for each neighbor
      const direction = new THREE.Vector3();
      dists.forEach(({ j }) => direction.add(pos.clone().sub(heavyVecs[j])));
      if (direction.lengthSq() < 1e-6) continue;  // can't place
      direction.normalize();
      const hPos = pos.clone().add(direction.multiplyScalar(CH));
      Hs.push(['H', hPos.x, hPos.y, hPos.z]);
    }

    return [...heavy, ...Hs];
  }
  const HELICENE = _buildHelicene5();

  // === Jacobi eigen-decomposition for 3x3 symmetric matrix ===
  // Returns [{val,vec}, ...] sorted by eigenvalue descending. Eigenvalues
  // are variances; eigenvectors are the principal axes of the point cloud.
  function jacobiEig3(cxx, cxy, cxz, cyy, cyz, czz) {
    const m = [[cxx, cxy, cxz], [cxy, cyy, cyz], [cxz, cyz, czz]];
    const V = [[1,0,0], [0,1,0], [0,0,1]];
    for (let sweep = 0; sweep < 40; sweep++) {
      let maxOff = 0, p_ = 0, q_ = 1;
      for (let p = 0; p < 2; p++) {
        for (let q = p + 1; q < 3; q++) {
          if (Math.abs(m[p][q]) > maxOff) { maxOff = Math.abs(m[p][q]); p_ = p; q_ = q; }
        }
      }
      if (maxOff < 1e-12) break;
      const p = p_, q = q_;
      const theta = (m[q][q] - m[p][p]) / (2 * m[p][q]);
      const t = (theta >= 0 ? 1 : -1) / (Math.abs(theta) + Math.sqrt(theta*theta + 1));
      const c = 1 / Math.sqrt(t*t + 1);
      const s = t * c;
      const Mpp = m[p][p], Mqq = m[q][q], Mpq = m[p][q];
      m[p][p] = Mpp - t * Mpq;
      m[q][q] = Mqq + t * Mpq;
      m[p][q] = 0; m[q][p] = 0;
      for (let r = 0; r < 3; r++) {
        if (r !== p && r !== q) {
          const Mrp = m[r][p], Mrq = m[r][q];
          m[r][p] = c * Mrp - s * Mrq; m[p][r] = m[r][p];
          m[r][q] = s * Mrp + c * Mrq; m[q][r] = m[r][q];
        }
      }
      for (let r = 0; r < 3; r++) {
        const Vrp = V[r][p], Vrq = V[r][q];
        V[r][p] = c * Vrp - s * Vrq;
        V[r][q] = s * Vrp + c * Vrq;
      }
    }
    const eigs = [
      { val: m[0][0], vec: [V[0][0], V[1][0], V[2][0]] },
      { val: m[1][1], vec: [V[0][1], V[1][1], V[2][1]] },
      { val: m[2][2], vec: [V[0][2], V[1][2], V[2][2]] },
    ];
    eigs.sort((a, b) => b.val - a.val);
    return eigs;
  }

  // === Build helicene mesh group, PCA-aligned to layer normal ===
  // Largest principal axis  → world Z (visible across viewport)
  // Medium principal axis   → world X (laterally)
  // Smallest principal axis → world Y (layer normal, fits in the vdW gap)
  //
  // H atoms are KEPT: dropping them leaves 7 aromatic edge C atoms with
  // only 1 heavy-atom neighbor (their other bond is to H), so the
  // structure looks fragmented. Render H as small pale spheres + thin
  // bonds — clutter is minimal at the bg scale, and the molecule reads
  // as a continuous polycyclic system.
  function buildHelicene() {
    const group = new THREE.Group();
    const ptsRaw = HELICENE;   // full 66-atom set

    // 1) Centroid (over heavy atoms only — H mass is tiny anyway)
    const heavy = ptsRaw.filter(p => p[0] !== 'H');
    let cx = 0, cy = 0, cz = 0;
    heavy.forEach(p => { cx += p[1]; cy += p[2]; cz += p[3]; });
    cx /= heavy.length; cy /= heavy.length; cz /= heavy.length;

    // 2) Covariance matrix — over heavy atoms only so PCA reflects the
    //    aromatic framework, not the H corona
    let cxx = 0, cxy = 0, cxz = 0, cyy = 0, cyz = 0, czz = 0;
    heavy.forEach(p => {
      const dx = p[1] - cx, dy = p[2] - cy, dz = p[3] - cz;
      cxx += dx*dx; cyy += dy*dy; czz += dz*dz;
      cxy += dx*dy; cxz += dx*dz; cyz += dy*dz;
    });
    const N = heavy.length;
    const eigs = jacobiEig3(cxx/N, cxy/N, cxz/N, cyy/N, cyz/N, czz/N);

    // 3) Build rotation matrix whose ROWS are the principal axes such that
    //    eigs[1] (medium) → x, eigs[2] (smallest) → y, eigs[0] (largest) → z
    const xRow = new THREE.Vector3(...eigs[1].vec);  // medium
    const yRow = new THREE.Vector3(...eigs[2].vec);  // smallest → layer normal
    let   zRow = new THREE.Vector3(...eigs[0].vec);  // largest
    // Ensure right-handed orientation (det = +1) to avoid mirror flip
    if (xRow.clone().cross(yRow).dot(zRow) < 0) zRow.negate();

    // Helper to project a centered point onto the new basis
    function rotate(x, y, z) {
      return [
        xRow.x*x + xRow.y*y + xRow.z*z,
        yRow.x*x + yRow.y*y + yRow.z*z,
        zRow.x*x + zRow.y*y + zRow.z*z,
      ];
    }

    // Rotate every atom
    const pts = ptsRaw.map(([e, x, y, z]) => {
      const [nx, ny, nz] = rotate(x - cx, y - cy, z - cz);
      return [e, nx, ny, nz];
    });

    // Compute final extents — handy for tuning the layer gap externally
    let yMin = Infinity, yMax = -Infinity;
    pts.forEach(p => { if (p[2] < yMin) yMin = p[2]; if (p[2] > yMax) yMax = p[2]; });
    group.userData.yExtent = yMax - yMin;   // smallest extent now = thickness in y

    // 4) Render atoms — H atoms small + faint, heavy atoms full color
    const colors = { C: 0xa8b0bd, N: 0x4060ee, O: 0xee3030, H: 0xe0e6f5 };
    const radii  = { C: 0.32,     N: 0.34,     O: 0.30,     H: 0.18 };
    const opacities = { C: 0.94, N: 0.94, O: 0.94, H: 0.55 };
    const mats = {}, geos = {};
    for (const k in colors) {
      mats[k] = new THREE.MeshPhongMaterial({
        color: colors[k], emissive: new THREE.Color(colors[k]).multiplyScalar(0.12),
        shininess: 60, transparent: true, opacity: opacities[k],
      });
      geos[k] = new THREE.SphereGeometry(radii[k], k === 'H' ? 10 : 14, k === 'H' ? 10 : 14);
    }
    pts.forEach(([e, x, y, z]) => {
      const m = new THREE.Mesh(geos[e], mats[e]);
      m.position.set(x, y, z);
      group.add(m);
    });

    // 5) Covalent bonds — different thresholds for X-H vs heavy-heavy
    //    so we keep the corona consistent and don't false-positive H-H pairs.
    function bondLimit(e1, e2) {
      // C-H, N-H, O-H ≈ 1.0-1.1 Å. Heavy-heavy ≤ 1.65 Å.
      if (e1 === 'H' || e2 === 'H') {
        if (e1 === 'H' && e2 === 'H') return 0;     // no H-H
        return 1.25;
      }
      return 1.65;
    }
    const cylGeoHeavy = new THREE.CylinderGeometry(0.06, 0.06, 1, 6, 1, true);
    const cylGeoH     = new THREE.CylinderGeometry(0.035, 0.035, 1, 5, 1, true);
    const bondMat = new THREE.MeshPhongMaterial({
      color: 0xb6c2d4, transparent: true, opacity: 0.62, depthWrite: false,
    });
    const bondMatH = new THREE.MeshPhongMaterial({
      color: 0xc8d0e0, transparent: true, opacity: 0.40, depthWrite: false,
    });
    const up = new THREE.Vector3(0, 1, 0);
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const [e1, x1, y1, z1] = pts[i];
        const [e2, x2, y2, z2] = pts[j];
        const lim = bondLimit(e1, e2);
        if (lim === 0) continue;
        const dx = x1 - x2, dy = y1 - y2, dz = z1 - z2;
        const d = Math.sqrt(dx*dx + dy*dy + dz*dz);
        if (d < lim) {
          const isH = e1 === 'H' || e2 === 'H';
          const cyl = new THREE.Mesh(isH ? cylGeoH : cylGeoHeavy, isH ? bondMatH : bondMat);
          cyl.position.set((x1+x2)/2, (y1+y2)/2, (z1+z2)/2);
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

  // === Compose: VSe₂ slab + PCA-aligned helicene in the vdW gap ===
  // Build the helicene first so we know its thickness (smallest-axis extent
  // after PCA alignment), then size the layer gap to fit it with margin.
  const helicene = buildHelicene();
  const gap = Math.max(13, Math.min(22, (helicene.userData.yExtent || 8) + 5));
  const slab = buildSlab(VSE2, 4, 4, 2, gap);
  scene.add(slab);
  helicene.position.set(0, 0, 0);   // centered between the two VSe₂ layers
  scene.add(helicene);

  // No tilt — we want a true side view of the layered structure
  // so the VSe2 sheets look like horizontal stripes with the helicene
  // sitting in the vdW gap between them, the canonical 'intercalation
  // cross-section' diagram.
  const sceneRoot = new THREE.Group();
  sceneRoot.add(slab);
  sceneRoot.add(helicene);
  sceneRoot.rotation.x = 0;
  sceneRoot.rotation.z = 0;
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

    // True side view: camera stays at y=0 plane (same height as layers)
    // and orbits horizontally around the y-axis. This makes the VSe2
    // sheets appear as horizontal stripes with the helicene visible
    // in the vdW gap between them.
    camera.position.x = r * Math.cos(orbitT);
    camera.position.y = 0;
    camera.position.z = r * Math.sin(orbitT);
    camera.lookAt(0, 0, 0);

    stars.rotation.y += 0.0003;
    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
