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

  // === DBPO helicene (C40H22N2O2) — copied directly from tmd-viewer ===
  // tmd-viewer/index.html has the same molecule with an EXPLICIT bond list,
  // so we can render it as a properly connected graph instead of relying on
  // a distance threshold that misses the 'long' single bonds linking the
  // two helical wings to the central pyrazine/N-oxide core.
  // Atom order: O O N N (4 heavy core) → C×40 → H×22  (total 66).
  // Bonds: edge list, indices into the atom array.
  const HELICENE_DATA = {
    atoms: [
      ['O',-2.801,-1.851,-1.733], ['O', 1.663, 3.069, 1.302],
      ['N',-1.596,-0.274, 0.151], ['N', 0.648, 1.231,-0.496],
      ['C',-2.063,-1.546, 0.570], ['C',-1.929,-2.055, 1.831],
      ['C',-2.434,-3.343, 2.148], ['C',-2.316,-3.892, 3.451],
      ['C',-2.826,-5.131, 3.739], ['C',-3.476,-5.879, 2.741],
      ['C',-3.592,-5.392, 1.467], ['C',-3.080,-4.113, 1.137],
      ['C',-3.182,-3.572,-0.169], ['C',-2.686,-2.336,-0.437],
      ['C',-1.790,-1.000,-2.147], ['C',-1.441,-0.953,-3.457],
      ['C',-0.468,-0.012,-3.886], ['C',-0.158, 0.145,-5.263],
      ['C', 0.683, 1.135,-5.689], ['C', 1.253, 2.026,-4.750],
      ['C', 1.035, 1.864,-3.406], ['C', 0.193, 0.824,-2.927],
      ['C',-0.074, 0.594,-1.541], ['C',-1.136,-0.207,-1.178],
      ['C', 2.043, 1.441,-0.481], ['C', 2.954, 0.774,-1.264],
      ['C', 4.332, 1.120,-1.241], ['C', 5.293, 0.425,-2.015],
      ['C', 6.621, 0.779,-1.966], ['C', 7.044, 1.849,-1.180],
      ['C', 6.145, 2.570,-0.440], ['C', 4.761, 2.220,-0.434],
      ['C', 3.811, 2.869, 0.379], ['C', 2.517, 2.449, 0.402],
      ['C', 0.494, 2.405, 1.615], ['C',-0.137, 2.706, 2.784],
      ['C',-1.412, 2.149, 3.048], ['C',-2.178, 2.577, 4.164],
      ['C',-3.470, 2.157, 4.335], ['C',-4.057, 1.280, 3.393],
      ['C',-3.325, 0.786, 2.342], ['C',-1.983, 1.195, 2.141],
      ['C',-1.185, 0.761, 1.033], ['C',-0.033, 1.445, 0.722],
      ['H',-1.459,-1.526, 2.534], ['H',-1.842,-3.383, 4.149],
      ['H',-2.676,-5.473, 4.642], ['H',-3.843,-6.741, 2.960],
      ['H',-4.014,-5.898, 0.737], ['H',-3.692,-4.075,-0.866],
      ['H',-1.902,-1.509,-4.101], ['H',-0.585,-0.470,-5.933],
      ['H', 0.869, 1.265,-6.584], ['H', 1.788, 2.777,-5.059],
      ['H', 1.470, 2.469,-2.764], ['H', 2.628, 0.082,-1.909],
      ['H', 4.983,-0.316,-2.571], ['H', 7.261, 0.281,-2.487],
      ['H', 7.981, 2.064,-1.159], ['H', 6.457, 3.345, 0.117],
      ['H', 4.065, 3.609, 0.959], ['H', 0.273, 3.355, 3.406],
      ['H',-1.710, 3.207, 4.819], ['H',-3.956, 2.460, 5.127],
      ['H',-4.996, 1.013, 3.496], ['H',-3.761, 0.173, 1.691],
    ],
    bonds: [
      [0,13],[0,14],[1,33],[1,34],[2,4],[2,23],[2,42],[3,22],[3,24],[3,43],
      [4,5],[4,13],[5,6],[5,44],[6,7],[6,11],[7,8],[7,45],[8,9],[8,46],
      [9,10],[9,47],[10,11],[10,48],[11,12],[12,13],[12,49],
      [14,15],[14,23],[15,16],[15,50],[16,17],[16,21],[17,18],[17,51],
      [18,19],[18,52],[19,20],[19,53],[20,21],[20,54],[21,22],[22,23],
      [24,25],[24,33],[25,26],[25,55],[26,27],[26,31],[27,28],[27,56],
      [28,29],[28,57],[29,30],[29,58],[30,31],[30,59],[31,32],[32,33],[32,60],
      [34,35],[34,43],[35,36],[35,61],[36,37],[36,41],[37,38],[37,62],
      [38,39],[38,63],[39,40],[39,64],[40,41],[40,65],[41,42],[42,43],
    ],
  };

  // === (procedural [5]helicene fallback — no longer used; kept commented out) ===
  /*
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
  */

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

  // === Build helicene mesh group from explicit DBPO data ===
  // Uses HELICENE_DATA.atoms (66 atoms: O,O,N,N,C×40,H×22) and
  // HELICENE_DATA.bonds (explicit edge list copied from tmd-viewer).
  // Sidesteps the distance-based bond detection that misses the long
  // single bonds connecting the two helicene wings to the central
  // pyrazine/N-oxide core.
  //
  // PCA-aligned to put the molecule's thinnest axis along the layer
  // normal (Y), so it sits flat in the vdW gap between VSe2 sheets.
  function buildHelicene() {
    const group = new THREE.Group();
    const ptsRaw = HELICENE_DATA.atoms;   // 66-atom set

    // 1) Centroid (over heavy atoms only — H mass is tiny anyway)
    const heavyIndices = ptsRaw.map((p, i) => p[0] !== 'H' ? i : -1).filter(i => i >= 0);
    let cx = 0, cy = 0, cz = 0;
    heavyIndices.forEach(i => { cx += ptsRaw[i][1]; cy += ptsRaw[i][2]; cz += ptsRaw[i][3]; });
    cx /= heavyIndices.length; cy /= heavyIndices.length; cz /= heavyIndices.length;
    const heavy = heavyIndices.map(i => ptsRaw[i]);

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

    // 5) Bonds — use the explicit edge list from tmd-viewer/DBPO.
    //    `pts` is already the rotated 66-atom array indexed identically
    //    to HELICENE_DATA.atoms, so bond indices resolve directly.
    const cylGeoHeavy = new THREE.CylinderGeometry(0.06, 0.06, 1, 6, 1, true);
    const cylGeoH     = new THREE.CylinderGeometry(0.035, 0.035, 1, 5, 1, true);
    const bondMat = new THREE.MeshPhongMaterial({
      color: 0xb6c2d4, transparent: true, opacity: 0.62, depthWrite: false,
    });
    const bondMatH = new THREE.MeshPhongMaterial({
      color: 0xc8d0e0, transparent: true, opacity: 0.40, depthWrite: false,
    });
    const up = new THREE.Vector3(0, 1, 0);

    for (const [a, b] of HELICENE_DATA.bonds) {
      const [ea, xa, ya, za] = pts[a];
      const [eb, xb, yb, zb] = pts[b];
      const dx = xa - xb, dy = ya - yb, dz = za - zb;
      const d = Math.sqrt(dx*dx + dy*dy + dz*dz);
      const isH = ea === 'H' || eb === 'H';
      const cyl = new THREE.Mesh(isH ? cylGeoH : cylGeoHeavy, isH ? bondMatH : bondMat);
      cyl.position.set((xa+xb)/2, (ya+yb)/2, (za+zb)/2);
      cyl.quaternion.setFromUnitVectors(up, new THREE.Vector3(xb-xa, yb-ya, zb-za).normalize());
      cyl.scale.y = d;
      group.add(cyl);
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

  // === Planetarium-style starfield ===========================
  // Three layered point clouds at different distances + sizes + colors
  // give the dome of a planetarium around the central TMD. Each layer
  // twinkles by independently sin-modulating its global opacity.
  function makeStarLayer(count, rMin, rMax, sizeMin, sizeMax, palette) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = rMin + Math.random() * (rMax - rMin);
      const t = Math.random() * Math.PI * 2;
      const p = Math.acos(2 * Math.random() - 1);
      pos[i*3]     = r * Math.sin(p) * Math.cos(t);
      pos[i*3 + 1] = r * Math.cos(p);
      pos[i*3 + 2] = r * Math.sin(p) * Math.sin(t);
      const c = palette[(Math.random() * palette.length) | 0];
      col[i*3] = c[0]; col[i*3+1] = c[1]; col[i*3+2] = c[2];
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color',    new THREE.BufferAttribute(col, 3));
    const mat = new THREE.PointsMaterial({
      size: sizeMin + Math.random() * (sizeMax - sizeMin),
      vertexColors: true, transparent: true, opacity: 0.85,
      sizeAttenuation: true, depthWrite: false,
    });
    const pts = new THREE.Points(geo, mat);
    return { points: pts, material: mat };
  }

  // Color palettes (RGB 0-1)
  const PALETTE_NEAR = [
    [1.0, 1.0, 1.0],   // pure white
    [0.92, 0.95, 1.0], // pale blue-white
    [1.0, 0.92, 0.78], // warm yellow
  ];
  const PALETTE_MID = [
    [0.78, 0.88, 1.0],
    [0.9,  0.95, 1.0],
    [1.0,  0.85, 0.6],
    [0.8,  0.7,  1.0], // faint violet
  ];
  const PALETTE_FAR = [
    [0.55, 0.7,  1.0], // distant blue
    [0.7,  0.55, 1.0], // distant violet
    [0.95, 0.88, 0.95],
  ];

  const starLayers = [
    makeStarLayer(280, 50,  90,  0.45, 0.55, PALETTE_NEAR),
    makeStarLayer(380, 90,  150, 0.30, 0.40, PALETTE_MID),
    makeStarLayer(450, 150, 240, 0.20, 0.28, PALETTE_FAR),
  ];
  starLayers.forEach(l => scene.add(l.points));
  // keep `stars` name for the existing animate() loop (rotate the near layer)
  const stars = starLayers[0].points;

  // === Constellation lines ===
  // For each near-layer star, connect it to its nearest neighbors within
  // a small radius so the night sky reads as a constellation map rather
  // than an isolated point cloud. Each star is capped at MAX_CONNS to
  // keep the graph sparse and pretty.
  function buildConstellations(points, maxDist, maxConns) {
    const pa = points.geometry.getAttribute('position');
    const N = pa.count;
    const v = [];
    for (let i = 0; i < N; i++) v.push(new THREE.Vector3(pa.getX(i), pa.getY(i), pa.getZ(i)));
    const used = new Int32Array(N);
    const verts = [];
    for (let i = 0; i < N; i++) {
      if (used[i] >= maxConns) continue;
      const cand = [];
      for (let j = 0; j < N; j++) {
        if (i === j) continue;
        if (used[j] >= maxConns) continue;
        const d = v[i].distanceTo(v[j]);
        if (d < maxDist) cand.push({ j, d });
      }
      cand.sort((a, b) => a.d - b.d);
      for (const c of cand) {
        if (used[i] >= maxConns) break;
        if (used[c.j] >= maxConns) continue;
        verts.push(v[i].x, v[i].y, v[i].z, v[c.j].x, v[c.j].y, v[c.j].z);
        used[i]++; used[c.j]++;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    const mat = new THREE.LineBasicMaterial({
      color: 0x9ad0ff, transparent: true, opacity: 0.20,
      depthWrite: false,
    });
    return new THREE.LineSegments(geo, mat);
  }
  const constellations = buildConstellations(starLayers[0].points, 28, 3);
  scene.add(constellations);

  // === Nebula clouds — translucent colored spheres far from the camera ===
  // They sit beyond the star layers and tint the void with soft color.
  function makeNebula(radius, x, y, z, color) {
    const geo = new THREE.SphereGeometry(radius, 24, 16);
    const mat = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: 0.06,
      side: THREE.BackSide, depthWrite: false,
    });
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    return m;
  }
  scene.add(makeNebula(120, -180,  60, -100, 0x5a3a8a));  // violet bloom upper-left
  scene.add(makeNebula(140,  150, -40, -120, 0x1a4a8a));  // deep blue lower-right
  scene.add(makeNebula(100,   30, 100,  200, 0x7a2a5a));  // magenta behind

  function onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  window.addEventListener('resize', onResize);
  onResize();

  // === Manual orbit controls — enabled only in bg-only mode ===
  // We *don't* use OrbitControls.autoRotate because its damping interacts
  // weirdly with toggling enabled. Instead we rotate the camera ourselves
  // around the target whenever the user isn't actively dragging — a
  // single 'start'/'end' pair from OrbitControls is enough to gate it.
  let controls = null;
  let userInteracting = false;
  if (typeof THREE.OrbitControls !== 'undefined') {
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enabled = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 8;
    controls.maxDistance = 80;   // keep TMD always within view
    controls.target.set(0, 0, 0);
    controls.addEventListener('start', () => { userInteracting = true; });
    controls.addEventListener('end',   () => { userInteracting = false; });
  }

  let inBgOnly = false;
  function syncControls() {
    const want = document.body.classList.contains('bg-only');
    if (want === inBgOnly) return;
    inBgOnly = want;
    if (controls) controls.enabled = want;
  }
  const observer = new MutationObserver(syncControls);
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  syncControls();

  // === Animate: tilted camera orbit, scene static ===
  const ORBIT_RADIUS = 38;
  const ORBIT_PERIOD_S = 90;
  const DOLLY_AMPL = 5;
  const DOLLY_PERIOD_S = 25;

  // Rotation rate for bg-only idle auto-rotate (matches normal-mode period)
  const BG_AUTO_OMEGA = (2 * Math.PI) / ORBIT_PERIOD_S;  // rad/sec
  let lastNow = performance.now();

  function animate(now) {
    requestAnimationFrame(animate);
    const dtSec = Math.min(0.05, (now - lastNow) / 1000);   // clamp to 50ms
    lastNow = now;

    if (inBgOnly && controls) {
      // While the user isn't dragging, rotate the camera around the y-axis
      // ourselves so the scene keeps spinning at the same pace as normal mode.
      if (!userInteracting) {
        const tx = controls.target.x, tz = controls.target.z;
        const dx = camera.position.x - tx;
        const dz = camera.position.z - tz;
        const r = Math.sqrt(dx*dx + dz*dz);
        const theta = Math.atan2(dz, dx) + BG_AUTO_OMEGA * dtSec;
        camera.position.x = tx + r * Math.cos(theta);
        camera.position.z = tz + r * Math.sin(theta);
      }
      controls.update();
    } else {
      // Default behavior: auto-orbit the side view.
      const t = now * 0.001;
      const orbitT = (t / ORBIT_PERIOD_S) * Math.PI * 2;
      const dolly = Math.sin((t / DOLLY_PERIOD_S) * Math.PI * 2) * DOLLY_AMPL;
      const r = ORBIT_RADIUS + dolly;
      camera.position.x = r * Math.cos(orbitT);
      camera.position.y = 0;
      camera.position.z = r * Math.sin(orbitT);
      camera.lookAt(0, 0, 0);
    }

    // Star layers: each rotates at a slightly different rate (parallax)
    // and twinkles its global opacity on a sine wave for that planetarium
    // shimmer. Different phase offsets per layer so they don't all pulse
    // in unison.
    const tStar = now * 0.001;
    starLayers[0].points.rotation.y += 0.00030;
    starLayers[1].points.rotation.y -= 0.00018;
    starLayers[2].points.rotation.y += 0.00010;
    starLayers[0].material.opacity = 0.80 + 0.18 * Math.sin(tStar * 0.9);
    starLayers[1].material.opacity = 0.65 + 0.20 * Math.sin(tStar * 0.7 + 1.4);
    starLayers[2].material.opacity = 0.55 + 0.22 * Math.sin(tStar * 0.5 + 2.8);

    // Constellations follow the near star layer so the pattern stays
    // pinned to its stars, and pulse with them so the network breathes.
    constellations.rotation.y = starLayers[0].points.rotation.y;
    constellations.material.opacity = 0.17 + 0.10 * Math.sin(tStar * 0.9);

    renderer.render(scene, camera);
  }
  animate(performance.now());
})();
