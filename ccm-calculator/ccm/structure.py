"""Structure input: compound name, SMILES, drawn structure, mol/SDF/XYZ.

Everything ends up as an RDKit molecule carrying a single 3D conformer,
which is what the CCM engine consumes.
"""

from __future__ import annotations

import io
import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, rdDetermineBonds

from .measure import (CCMResult, DEFAULT_GROUPS, EXHAUSTIVE_LIMIT, ccm,
                      element_permutations, graph_automorphisms,
                      permutation_count, refinement_classes,
                      refinement_permutations, restrict_permutations)

RDLogger.DisableLog("rdApp.*")

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
OPSIN = "https://www.ebi.ac.uk/opsin/ws"
TIMEOUT = 20

# Pyykko covalent radii (A), enough elements for organic / organometallic work
COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84, "C": 0.76,
    "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58, "Na": 1.66, "Mg": 1.41,
    "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Ar": 1.06,
    "K": 2.03, "Ca": 1.76, "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39,
    "Mn": 1.50, "Fe": 1.42, "Co": 1.38, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20, "Kr": 1.16,
    "Rb": 2.20, "Sr": 1.95, "Y": 1.90, "Zr": 1.75, "Nb": 1.64, "Mo": 1.54,
    "Ru": 1.46, "Rh": 1.42, "Pd": 1.39, "Ag": 1.45, "Cd": 1.44, "In": 1.42,
    "Sn": 1.39, "Sb": 1.39, "Te": 1.38, "I": 1.39, "Xe": 1.40, "Cs": 2.44,
    "Ba": 2.15, "La": 2.07, "Hf": 1.75, "Ta": 1.70, "W": 1.62, "Re": 1.51,
    "Os": 1.44, "Ir": 1.41, "Pt": 1.36, "Au": 1.36, "Hg": 1.32, "Tl": 1.45,
    "Pb": 1.46, "Bi": 1.48,
}


class StructureError(RuntimeError):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ccm-tool/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
        return fh.read()


# --------------------------------------------------------------------------
# name resolution
# --------------------------------------------------------------------------

def resolve_name(name: str, prefer_3d: bool = False) -> tuple[Chem.Mol, str]:
    """Compound name -> molecule.

    Tries, in order:
      1. PubChem isomeric SMILES
      2. OPSIN (IUPAC name parser at EBI)
      3. PubChem 3D conformer (SDF)

    The connectivity route comes first *on purpose*.  PubChem also serves a
    ready-made 3D conformer, but taking it would mean the "compound name" tab
    measured a different geometry from the "SMILES" tab for the same molecule
    -- and CCM is a property of a geometry, so the two would disagree, often
    by a factor of two or three.  Resolving the name to a SMILES and then
    running the same ETKDG/MMFF pipeline as every other input keeps the four
    input routes comparable.  Pass ``prefer_3d=True`` to use PubChem's
    deposited geometry instead.

    Note: the name must specify the stereochemistry, e.g. "(R)-glycidol"
    or "(S)-BINAP".  A name without stereodescriptors gives whatever
    PubChem stores, which may be the racemate / unspecified form.
    """
    q = urllib.parse.quote(name.strip(), safe="")
    errors = []

    def pubchem_3d():
        sdf = _get(f"{PUBCHEM}/name/{q}/SDF?record_type=3d").decode("utf-8", "replace")
        mol = Chem.MolFromMolBlock(sdf, removeHs=False, sanitize=True)
        if mol is not None and mol.GetNumConformers() and mol.GetNumAtoms() > 1:
            Chem.AssignStereochemistryFrom3D(mol)
            return mol, "PubChem 3D conformer (deposited geometry)"
        return None

    if prefer_3d:
        try:
            hit = pubchem_3d()
            if hit:
                return hit
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"PubChem 3D: {exc}")

    # 1. isomeric SMILES from PubChem
    for prop in ("IsomericSMILES", "SMILES", "CanonicalSMILES"):
        try:
            smi = _get(f"{PUBCHEM}/name/{q}/property/{prop}/TXT")
            smi = smi.decode("utf-8", "replace").strip().splitlines()[0].strip()
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                return mol, f"PubChem {prop}: {smi}"
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"PubChem {prop}: {exc}")

    # 2. OPSIN, for systematic IUPAC names PubChem does not index
    try:
        data = json.loads(_get(f"{OPSIN}/{q}.json").decode("utf-8", "replace"))
        smi = data.get("smiles")
        if smi:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                return mol, f"OPSIN: {smi}"
    except Exception as exc:                                    # noqa: BLE001
        errors.append(f"OPSIN: {exc}")

    # 3. last resort: whatever geometry PubChem has
    if not prefer_3d:
        try:
            hit = pubchem_3d()
            if hit:
                return hit
        except Exception as exc:                                # noqa: BLE001
            errors.append(f"PubChem 3D: {exc}")

    raise StructureError(
        f"化合物名 {name!r} を解決できませんでした（PubChem と OPSIN を検索）。"
        "英語名・IUPAC 名で、立体記述子を含めて入力してください（例: (R)-glycidol）。"
    )


def resolve_smiles(smiles: str) -> tuple[Chem.Mol, str]:
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise StructureError(f"SMILES を解釈できません: {smiles!r}")
    return mol, f"SMILES: {smiles.strip()}"


def resolve_molblock(text: str) -> tuple[Chem.Mol, str]:
    # JSME hands back a block with no trailing newline, which RDKit rejects.
    # Keep the leading (empty) title line, normalise line endings, end with \n.
    text = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    mol = Chem.MolFromMolBlock(text, removeHs=False, sanitize=True)
    if mol is None and not text.startswith("\n"):
        # the title line was trimmed away somewhere upstream; put it back
        mol = Chem.MolFromMolBlock("\n" + text, removeHs=False, sanitize=True)
        if mol is not None:
            text = "\n" + text
    if mol is None:
        mol = Chem.MolFromMolBlock(text, removeHs=False, sanitize=False)
        if mol is not None:
            Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL
                             ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    if mol is None:
        raise StructureError("mol/SDF を解釈できませんでした")
    if mol.GetNumConformers():
        conf = mol.GetConformer()
        if not conf.Is3D() or _is_flat(mol):
            mol.RemoveAllConformers()
        else:
            Chem.AssignStereochemistryFrom3D(mol)
    return mol, "mol/SDF block"


def _is_flat(mol: Chem.Mol, tol: float = 1e-4) -> bool:
    pos = mol.GetConformer().GetPositions()
    return bool(np.ptp(pos[:, 2]) < tol)


def _bonds_from_geometry(mol: Chem.Mol, scale: float = 1.25) -> Chem.Mol:
    """Covalent-radius fallback when rdDetermineBonds is unhappy."""
    pos = mol.GetConformer().GetPositions()
    em = Chem.RWMol(mol)
    n = mol.GetNumAtoms()
    for i in range(n):
        ri = COVALENT_RADII.get(mol.GetAtomWithIdx(i).GetSymbol(), 1.5)
        for j in range(i + 1, n):
            rj = COVALENT_RADII.get(mol.GetAtomWithIdx(j).GetSymbol(), 1.5)
            if np.linalg.norm(pos[i] - pos[j]) < scale * (ri + rj):
                em.AddBond(i, j, Chem.BondType.SINGLE)
    out = em.GetMol()
    try:
        Chem.SanitizeMol(out, Chem.SanitizeFlags.SANITIZE_ALL
                         ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    except Exception:                                           # noqa: BLE001
        pass
    return out


def resolve_xyz(text: str) -> tuple[Chem.Mol, str]:
    lines = [ln for ln in text.strip().splitlines()]
    if not lines:
        raise StructureError("XYZ が空です")
    try:
        natoms = int(lines[0].split()[0])
        body = lines[2:2 + natoms]
    except (ValueError, IndexError):                             # header-less xyz
        body = [ln for ln in lines if len(ln.split()) >= 4]
        natoms = len(body)

    em = Chem.RWMol()
    conf = Chem.Conformer(natoms)
    for k, ln in enumerate(body):
        parts = ln.split()
        sym = parts[0].strip().capitalize()
        if sym not in COVALENT_RADII and not sym.isalpha():
            raise StructureError(f"元素記号を認識できません: {ln!r}")
        em.AddAtom(Chem.Atom(sym))
        conf.SetAtomPosition(k, tuple(float(v) for v in parts[1:4]))
    mol = em.GetMol()
    conf.Set3D(True)
    mol.AddConformer(conf, assignId=True)

    try:
        rdDetermineBonds.DetermineConnectivity(mol)
        Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL
                         ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
        note = "XYZ (connectivity perceived by RDKit)"
    except Exception:                                           # noqa: BLE001
        mol = _bonds_from_geometry(mol)
        note = "XYZ (connectivity from covalent radii)"
    return mol, note


# --------------------------------------------------------------------------
# multi-record SDF: one molecule, many conformers
# --------------------------------------------------------------------------

# Property fields that conformer generators commonly use for the energy.
# Checked in order; the first one present on every record wins.
ENERGY_PROPS = (
    "energy", "Energy", "ENERGY",
    "E", "e_pot",
    "r_mmod_Potential_Energy-OPLS3", "r_mmod_Potential_Energy-OPLS_2005",
    "r_mmod_Relative_Energy-OPLS3",
    "r_epik_Ionization_Penalty",
    "MMFF_Energy", "mmff_energy", "UFF_Energy",
    "PM6_Energy", "SCF_Energy", "Total_Energy", "total_energy",
    "DFT_Energy", "Gibbs_Free_Energy", "free_energy", "G", "dG",
    "CONFORMER_ENERGY", "conformer_energy",
)


def is_multi_record_sdf(text: str) -> bool:
    """True when the text holds more than one ``$$$$``-terminated record."""
    return text.count("$$$$") >= 2


def _record_energy(mol: Chem.Mol, prop: str = None):
    names = (prop,) if prop else ENERGY_PROPS
    for name in names:
        if name and mol.HasProp(name):
            try:
                return float(mol.GetProp(name).strip())
            except (ValueError, TypeError):
                continue
    return None


def resolve_sdf_ensemble(text: str, energy_prop: str = None):
    """Multi-record SDF -> one molecule carrying every record as a conformer.

    This is the route for coordinates that came from somewhere better than
    ETKDG/MMFF.  Zahrt and Denmark, for instance, searched conformers with
    Macromodel/OPLS3, re-optimised with PM6 and took free energies from
    M06-2X; none of that is reproducible with a force field, so the honest
    thing is to let those geometries -- and those energies -- in directly.

    Every record must be the same molecule (same canonical SMILES); a file
    holding several different species is a batch, not an ensemble, and is
    rejected rather than silently averaged.  Energies are read from an SDF
    property field (``energy_prop``, or the first recognised name in
    ``ENERGY_PROPS``) and are used for the Boltzmann weights instead of
    MMFF94 single points.
    """
    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(text.encode("utf-8")),
                                         removeHs=False, sanitize=True)
    records, energies, skipped = [], [], 0
    for m in supplier:
        if m is None or not m.GetNumConformers():
            skipped += 1
            continue
        records.append(m)
        energies.append(_record_energy(m, energy_prop))
    if not records:
        raise StructureError("SDF から構造を 1 つも読めませんでした")

    base = Chem.Mol(records[0])
    ref = Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(base)))
    base.RemoveAllConformers()
    kept = 0
    for m in records:
        if Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(m))) != ref:
            raise StructureError(
                "SDF の各レコードが同じ分子ではありません。配座アンサンブルとして"
                "読むには全レコードが同一分子である必要があります"
                "（複数分子をまとめて処理するなら --batch を使ってください）。")
        conf = Chem.Conformer(m.GetConformer())
        conf.Set3D(True)
        base.AddConformer(conf, assignId=True)
        kept += 1
    Chem.AssignStereochemistryFrom3D(base)

    have = [e for e in energies if e is not None]
    external = energies if len(have) == kept else None
    note = f"SDF 配座アンサンブル（{kept} レコード）"
    if external is not None:
        note += f" ＋ 外部エネルギー（{energy_prop or '自動検出'}）"
    elif have:
        note += "（エネルギー欄が一部のレコードにしか無いため MMFF94 で計算します）"
    if skipped:
        note += f"、読めなかったレコード {skipped} 件"
    return base, note, external


# --------------------------------------------------------------------------
# CCM_C2-A: the anion
# --------------------------------------------------------------------------

# Zahrt & Denmark's best-performing variant is computed on the *conjugate
# base* of the catalyst (their catalysts are BINOL-derived phosphoric acids).
# These patterns cover the acidic O-H of phosphoric/phosphonic, carboxylic
# and sulfonic acids; the catalytic proton of the paper is the first one.
ACIDIC_OH = (
    "[OX2H1][PX4]=[OX1]",
    "[OX2H1][SX4](=[OX1])=[OX1]",
    "[OX2H1][CX3]=[OX1]",
    "[OX2H1][SX3]=[OX1]",
)


def deprotonate(mol: Chem.Mol) -> tuple:
    """Remove acidic O-H protons -> the anion (Zahrt-Denmark ``CCM_C2-A``).

    Returns ``(mol, removed_indices)``.  Nothing is done, and no error is
    raised, if the molecule has no acidic proton -- the caller reports that.
    """
    edit = Chem.RWMol(mol)
    targets: set = set()
    for smarts in ACIDIC_OH:
        patt = Chem.MolFromSmarts(smarts)
        if patt is None:
            continue
        for match in edit.GetSubstructMatches(patt):
            targets.add(match[0])
    if not targets:
        return mol, []

    drop = []
    for idx in sorted(targets):
        atom = edit.GetAtomWithIdx(idx)
        atom.SetFormalCharge(-1)
        atom.SetNumExplicitHs(0)
        atom.SetNoImplicit(True)
        for nb in atom.GetNeighbors():
            if nb.GetAtomicNum() == 1:
                drop.append(nb.GetIdx())
    for idx in sorted(drop, reverse=True):
        edit.RemoveAtom(idx)

    out = edit.GetMol()
    try:
        Chem.SanitizeMol(out)
    except Exception as exc:                                    # noqa: BLE001
        raise StructureError(f"アニオン体を生成できませんでした: {exc}") from exc
    return out, sorted(targets)


# --------------------------------------------------------------------------
# CCM_Chiraphore: measure only part of the molecule
# --------------------------------------------------------------------------

def subset_indices(mol: Chem.Mol, spec) -> list:
    """Atoms selected by a SMARTS pattern or an explicit index list.

    ``spec`` may be a sequence of integers, a comma/space separated string of
    integers, or a SMARTS pattern (the union of every match is taken).
    Indices are 0-based into the atom set actually being measured, i.e. the
    numbering shown in the per-atom contribution table.
    """
    if spec is None:
        return list(range(mol.GetNumAtoms()))
    if not isinstance(spec, str):
        idx = [int(i) for i in spec]
    elif re.fullmatch(r"[\d\s,]+", spec.strip() or "x"):
        idx = [int(t) for t in re.split(r"[\s,]+", spec.strip()) if t]
    else:
        patt = Chem.MolFromSmarts(spec)
        if patt is None:
            raise StructureError(f"SMARTS を解釈できません: {spec!r}")
        hits = mol.GetSubstructMatches(patt, uniquify=True)
        idx = sorted({a for match in hits for a in match})
        if not idx:
            raise StructureError(
                f"部分構造 {spec!r} は測定対象の原子集合に一致しませんでした"
                "（水素を含めるか、重原子のみかで一致が変わります）。")
    bad = [i for i in idx if not 0 <= i < mol.GetNumAtoms()]
    if bad:
        raise StructureError(
            f"原子番号 {bad} は範囲外です（0〜{mol.GetNumAtoms() - 1}）。")
    if len(idx) < 3:
        raise StructureError("部分集合の原子が 3 個未満では CCM を定義できません。")
    return sorted(set(idx))


# --------------------------------------------------------------------------
# 3D embedding
# --------------------------------------------------------------------------

def mirror_image(mol: Chem.Mol) -> Chem.Mol:
    """The enantiomer: invert every tetrahedral centre.

    Double-bond (E/Z) stereo is deliberately left alone -- a reflection does
    not interconvert cis and trans.
    """
    out = Chem.Mol(mol)
    cw, ccw = Chem.ChiralType.CHI_TETRAHEDRAL_CW, Chem.ChiralType.CHI_TETRAHEDRAL_CCW
    for a in out.GetAtoms():
        tag = a.GetChiralTag()
        if tag == cw:
            a.SetChiralTag(ccw)
        elif tag == ccw:
            a.SetChiralTag(cw)
    return out


def canonical_enantiomer(mol: Chem.Mol) -> tuple[Chem.Mol, bool]:
    """Pick a fixed one of the two enantiomers, deterministically.

    CCM is a mirror invariant: a structure and its reflection are exactly
    equally far from the nearest achiral structure.  The *pipeline*, however,
    is not mirror-symmetric -- ETKDG explores the two enantiomers' conformer
    spaces independently, so (R)- and (S)-2-butanol came out at 2.02 and 1.93
    (heavy atoms) and 4.56 and 8.43 (all atoms) purely because a different
    conformer happened to win on MMFF energy.  Measuring a fixed enantiomer
    removes that artefact and makes the two inputs agree exactly.

    Returns ``(mol, flipped)``.
    """
    mirrored = mirror_image(mol)
    try:
        here = Chem.MolToSmiles(mol)
        there = Chem.MolToSmiles(mirrored)
    except Exception:                                           # noqa: BLE001
        return mol, False
    if there < here:
        return mirrored, True
    return mol, False


def embed_3d(mol: Chem.Mol, seed: int = 0xC0FFEE, optimise: bool = True,
             n_conformers: int = 1, prune_rms: float = 0.5
             ) -> tuple[Chem.Mol, list[str]]:
    """Add hydrogens and generate 3D coordinates with ETKDGv3 + MMFF94."""
    notes: list[str] = []
    mol = Chem.AddHs(mol, addCoords=bool(mol.GetNumConformers()))

    if mol.GetNumConformers() == 0:
        params = AllChem.ETKDGv3()
        params.randomSeed = seed
        params.useSmallRingTorsions = True
        params.enforceChirality = True
        # NB: do *not* set params.pruneRmsThresh.  ETKDG prunes on the raw
        # embedded geometries, before the force field has moved anything, and
        # for a small molecule like alanine it then collapses 30 conformers to
        # 1 -- destroying exactly the spread (CCM 1.6 to 10.3) that the
        # ensemble statistics exist to report.  Deduplicate after optimisation
        # instead, which is also what Zahrt and Denmark did (0.5 A RMSD).
        cids = AllChem.EmbedMultipleConfs(mol, numConfs=max(1, n_conformers),
                                          params=params)
        if not cids:
            params.useRandomCoords = True
            cids = AllChem.EmbedMultipleConfs(mol, numConfs=max(1, n_conformers),
                                              params=params)
        if not cids:
            raise StructureError("この分子の 3D 座標を発生できませんでした")
        notes.append(f"ETKDGv3 で {len(cids)} 配座を発生させました")
        if optimise:
            # Ask first rather than catching a failure: for a molecule MMFF94
            # cannot parameterise (boron, say) MMFFOptimizeMoleculeConfs does
            # not raise -- it returns a non-zero status and leaves the geometry
            # untouched, which used to be reported as "did not converge".
            try:
                if AllChem.MMFFHasAllMoleculeParams(mol):
                    res = AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=2000)
                    if any(r[0] != 0 for r in res):
                        notes.append("MMFF94 の構造最適化が一部の配座で収束しませんでした")
                    else:
                        notes.append("MMFF94 で構造最適化しました（収束）")
                else:
                    AllChem.UFFOptimizeMoleculeConfs(mol, maxIters=2000)
                    notes.append("MMFF94 にこの分子のパラメータが無いため "
                                 "UFF で構造最適化しました")
            except Exception:                                   # noqa: BLE001
                AllChem.UFFOptimizeMoleculeConfs(mol, maxIters=2000)
                notes.append("MMFF が使えないため UFF で最適化しました")
        if prune_rms > 0:
            dropped = _dedupe_conformers(mol, prune_rms)
            if dropped:
                notes.append(f"最適化後に RMSD {prune_rms} Å 以内の重複配座を "
                             f"{dropped} 個除きました（残り {mol.GetNumConformers()} 個）")
    else:
        notes.append("入力に含まれる 3D 座標をそのまま使用しました")
    return mol, notes


def _kabsch_rmsd(A: np.ndarray, B: np.ndarray) -> float:
    """All-atom RMSD after optimal rigid superposition (rotations only)."""
    A = A - A.mean(axis=0)
    B = B - B.mean(axis=0)
    U, S, Vt = np.linalg.svd(A.T @ B)
    d = np.sign(np.linalg.det(U @ Vt))
    S = S.copy()
    S[-1] *= d
    sq = max(0.0, float((A * A).sum() + (B * B).sum() - 2.0 * S.sum()))
    return math.sqrt(sq / len(A))


def _dedupe_conformers(mol: Chem.Mol, threshold: float, cap: int = 400) -> int:
    """Drop conformers within ``threshold`` A (all-atom RMSD) of a kept one.

    Runs *after* the force field, so it measures the geometries that are
    actually reported.  Superposition is rigid-body only -- RDKit's
    ``GetBestRMS`` would additionally search over symmetry-equivalent atom
    labellings, but that search is combinatorial and hangs on ligands with
    several tert-butyl groups.  The cheap version can only ever keep a
    duplicate, never discard a genuinely different conformer, which is the
    safe direction to err in.
    """
    ids = [c.GetId() for c in mol.GetConformers()]
    if len(ids) < 2 or len(ids) > cap:
        return 0
    coords = {cid: mol.GetConformer(cid).GetPositions() for cid in ids}
    keep: list[int] = []
    for cid in ids:
        if all(_kabsch_rmsd(coords[cid], coords[ref]) > threshold for ref in keep):
            keep.append(cid)
    dropped = 0
    for cid in ids:
        if cid not in keep:
            mol.RemoveConformer(cid)
            dropped += 1
    return dropped


# --------------------------------------------------------------------------
# top level
# --------------------------------------------------------------------------

@dataclass
class Analysis:
    result: CCMResult
    mol: Chem.Mol            # the atom set actually measured (3D)
    full_mol: Chem.Mol       # the molecule with all hydrogens
    smiles: str
    formula: str
    source: str
    include_hydrogens: bool
    groups: tuple
    ccm_heavy: float = float("nan")     # always reported, both atom sets
    ccm_all: float = float("nan")
    conformer_values: list = field(default_factory=list)
    conformer_energies: list = field(default_factory=list)
    # The six conformer-ensemble descriptors of Zahrt & Denmark, Tetrahedron
    # 2019, 75, 1841: plain mean and s.d. over the ensemble (CCM_A, CCM_SD)
    # and their Boltzmann-weighted counterparts (CCM_BA, CCM_BSD).  In their
    # random-forest models CCM_BSD -- the *spread*, a proxy for how floppy the
    # catalyst is -- carried more weight than the mean.  The remaining two are
    # not statistics but different atom sets: CCM_Chiraphore (`subset=`) and
    # CCM_C2-A (`anion=True`), the latter being their best single variant.
    ccm_mean: float = float("nan")          # CCM_A
    ccm_sd: float = float("nan")            # CCM_SD
    boltzmann_mean: float = float("nan")    # CCM_BA
    boltzmann_sd: float = float("nan")      # CCM_BSD
    descriptor: str = "CCM"                 # which variant this run computed
    exact: bool = True                      # False = assignment search (upper bound)
    use_mass: bool = False
    subset_size: int = 0                    # 0 = whole molecule
    temperature: float = 298.15
    energy_source: str = "MMFF94"
    notes: list = field(default_factory=list)


def _working_mol(mol3d: Chem.Mol, include_hydrogens: bool,
                 conf_id: int = -1) -> Chem.Mol:
    single = Chem.Mol(mol3d)
    conf = Chem.Conformer(mol3d.GetConformer(conf_id))
    single.RemoveAllConformers()
    single.AddConformer(conf, assignId=True)
    if include_hydrogens:
        return single
    heavy = Chem.RemoveAllHs(single, sanitize=False)
    try:
        Chem.SanitizeMol(heavy, Chem.SanitizeFlags.SANITIZE_ALL
                         ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    except Exception:                                           # noqa: BLE001
        pass
    return heavy


def _submol(mol: Chem.Mol, keep) -> Chem.Mol:
    """The molecule reduced to ``keep`` (ascending), for display and export."""
    keep = sorted(set(int(i) for i in keep))
    edit = Chem.RWMol(mol)
    for idx in sorted(set(range(mol.GetNumAtoms())) - set(keep), reverse=True):
        edit.RemoveAtom(idx)
    out = edit.GetMol()
    try:
        Chem.SanitizeMol(out, Chem.SanitizeFlags.SANITIZE_ALL
                         ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES
                         ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE)
    except Exception:                                           # noqa: BLE001
        pass
    return out


# kcal/mol per unit, for energies read out of an SDF property field
ENERGY_UNITS = {"kcal": 1.0, "kcal/mol": 1.0,
                "kj": 1.0 / 4.184, "kj/mol": 1.0 / 4.184,
                "hartree": 627.5094740631, "au": 627.5094740631,
                "ev": 23.060547830619, "k": 0.0019872041}

GAS_CONSTANT = 0.0019872041          # kcal / (mol K)


def _resolve_input(source_kind: str, value: str, prefer_3d: bool,
                   energy_prop: str = None):
    """``(mol, source, external_energies)`` for any of the input routes."""
    if source_kind in ("mol", "sdf") and is_multi_record_sdf(value):
        return resolve_sdf_ensemble(value, energy_prop)
    resolver = {
        "name": (lambda v: resolve_name(v, prefer_3d=prefer_3d)),
        "smiles": resolve_smiles,
        "mol": resolve_molblock,
        "sdf": resolve_molblock,
        "xyz": resolve_xyz,
    }.get(source_kind)
    if resolver is None:
        raise StructureError(f"未知の入力形式です: {source_kind!r}")
    mol, source = resolver(value)
    return mol, source, None


def _unspecified_stereo_notes(mol: Chem.Mol) -> list:
    """Warn about stereochemistry the input did not pin down.

    ``FindMolChiralCenters`` only sees tetrahedral centres, which silently
    misses axial chirality: RDKit does not carry an allene's stereochemistry
    through SMILES parsing (``F/C=C=C/F`` canonicalises to ``FC=C=CF``), so an
    axially chiral molecule was embedded as an achiral conformer and the tool
    reported **CCM = 0 with no warning at all**.  ``FindPotentialStereo`` sees
    every kind of stereo element, specified or not.
    """
    try:
        elements = list(Chem.FindPotentialStereo(mol))
    except Exception:                                           # noqa: BLE001
        elements = []
    atoms, bonds = [], []
    for e in elements:
        if str(e.specified) != "Unspecified":
            continue
        (atoms if str(e.type).startswith("Atom") else bonds).append(int(e.centeredOn))
    if not atoms and not bonds:
        return []

    notes = []
    if atoms:
        notes.append(
            "原子 " + ", ".join(str(i) for i in atoms)
            + " の立体が未指定です。配置は任意に選ばれました。"
            "エナンチオマー同士の CCM は同じですが、ジアステレオマーは異なります。")
    if bonds:
        cumulene = any(
            all(nb.GetIdx() != j and mol.GetBondBetweenAtoms(i, nb.GetIdx())
                and mol.GetBondBetweenAtoms(i, nb.GetIdx()).GetBondType()
                == Chem.BondType.DOUBLE
                for nb in [n for n in mol.GetAtomWithIdx(i).GetNeighbors()])
            and mol.GetAtomWithIdx(i).GetDegree() == 2
            for i in bonds for j in [i])
        notes.append(
            "結合 " + ", ".join(str(i) for i in bonds)
            + " の二重結合まわりの立体が未指定です。任意の配置で計算しています。")
        if cumulene:
            notes.append(
                "**アレン（累積二重結合）の軸不斉は SMILES から復元できません。**"
                "RDKit は `F/C=C=C/F` を `FC=C=CF` に落としてしまうため、"
                "アキラルな配座が発生し CCM が 0 になります。"
                "軸不斉のある分子は mol/SDF/XYZ で 3D 座標を与えてください。")
    return notes


def analyse(source_kind: str,
            value: str,
            include_hydrogens: bool = False,
            groups: tuple = DEFAULT_GROUPS,
            n_conformers: int = 10,
            seed: int = 0xC0FFEE,
            topology: str = "bonds",
            prefer_3d: bool = False,
            use_mass: bool = False,
            subset=None,
            anion: bool = False,
            energy_prop: str = None,
            energy_unit: str = "kcal",
            temperature: float = 298.15) -> Analysis:
    """Resolve an input, build 3D coordinates and compute the CCM.

    ``subset``  SMARTS or atom indices -> CCM_Chiraphore (part of the molecule)
    ``anion``   deprotonate the acidic O-H first -> CCM_C2-A
    ``use_mass`` centre on the centre of mass (CSM ``--use-mass``)
    """
    mol, source, external = _resolve_input(source_kind, value, prefer_3d,
                                           energy_prop)
    notes: list[str] = []

    if temperature <= 0:
        raise StructureError("温度は正の値で指定してください（K）。")
    scale = ENERGY_UNITS.get(str(energy_unit).lower())
    if scale is None:
        raise StructureError(
            f"エネルギーの単位を認識できません: {energy_unit!r}"
            f"（{', '.join(sorted(set(ENERGY_UNITS)))} のいずれか）")

    if anion:
        mol, removed = deprotonate(mol)
        if removed:
            notes.append(
                f"酸性プロトンを外したアニオン体で計算しています（脱プロトン化した "
                f"O: {', '.join(str(i) for i in removed)}）。"
                "Zahrt–Denmark の CCM_C2-A に相当します。")
        else:
            notes.append(
                "--anion を指定されましたが、酸性の O–H（リン酸・カルボン酸・"
                "スルホン酸型）が見つからないため中性のまま計算しました。")

    notes.extend(_unspecified_stereo_notes(mol))

    # Renumber to a canonical atom order before embedding, so that two ways of
    # writing the same molecule ("C[C@H](N)C(=O)O" and "N[C@@H](C)C(O)=O")
    # generate the same conformers and therefore the same CCM.  For the same
    # reason, measure a fixed one of the two enantiomers.
    if mol.GetNumConformers() == 0:
        mol, flipped = canonical_enantiomer(mol)
        if flipped:
            notes.append(
                "エナンチオマー同士は CCM が等しいため、配座発生の再現性を保つ目的で"
                "鏡像体の側を測定しました（値は入力した鏡像異性体のものと同一です）。")
        order = list(Chem.CanonicalRankAtoms(mol, breakTies=True))
        mol = Chem.RenumberAtoms(mol, [order.index(i) for i in range(len(order))])

    mol3d, embed_notes = embed_3d(mol, seed=seed, n_conformers=n_conformers)
    notes.extend(embed_notes)

    smiles = Chem.MolToSmiles(Chem.RemoveHs(Chem.Mol(mol3d)))
    formula = Chem.rdMolDescriptors.CalcMolFormula(mol3d)

    def permutations_for(work: Chem.Mol, symbols):
        """``(perms, labels)``; ``perms is None`` -> use the assignment search."""
        if topology == "bonds":
            return graph_automorphisms(work), None
        labels = (list(symbols) if topology == "element"
                  else [str(c) for c in refinement_classes(work)])
        if permutation_count(labels) > EXHAUSTIVE_LIMIT:
            return None, labels
        return element_permutations(labels), labels

    def measure(conf_id: int, with_h: bool):
        work = _working_mol(mol3d, with_h, conf_id)
        coords = work.GetConformer().GetPositions()
        symbols = [a.GetSymbol() for a in work.GetAtoms()]
        masses = [a.GetMass() for a in work.GetAtoms()] if use_mass else None
        perms, labels = permutations_for(work, symbols)

        sel = subset_indices(work, subset) if subset is not None else None
        if sel is not None:
            if perms is not None:
                perms = restrict_permutations(perms, sel)
            if labels is not None:
                labels = [labels[i] for i in sel]
            coords = coords[sel]
            symbols = [symbols[i] for i in sel]
            if masses is not None:
                masses = [masses[i] for i in sel]
            work = _submol(work, sel)

        return ccm(coords, symbols, perms, groups=groups, masses=masses,
                   classes=labels), work

    conf_ids = [c.GetId() for c in mol3d.GetConformers()]
    if external is not None and len(external) == len(conf_ids):
        energies = [float(e) * scale for e in external]
        energy_source = f"外部（SDF プロパティ, {energy_unit}）"
    else:
        energies, energy_source = _conformer_energies(mol3d, conf_ids)

    # the reported structure is the lowest-energy conformer, not the one with
    # the smallest CCM: CCM is a property of a geometry, so the geometry has
    # to be chosen on physical grounds.
    if energies:
        primary = conf_ids[int(np.argmin(energies))]
    else:
        primary = conf_ids[0]
        if len(conf_ids) > 1:
            notes.append(
                "この分子の配座エネルギーを出せる力場がありません"
                "（MMFF94 はホウ素などのパラメータを持たず、UFF も失敗しました）。"
                "**表示値は最安定配座ではなく、ETKDG が最初に出した配座のもの**です。"
                "Boltzmann 統計 (CCM_BA / CCM_BSD) も出せません。配座を選ぶ根拠が"
                "要る場合は、外部で最適化した構造を mol/SDF で与えてください。")

    result, best_mol = measure(primary, include_hydrogens)
    # The other atom set is a courtesy figure, so a failure there (typically a
    # permutation explosion once hydrogens are in play) must not take down the
    # measurement the user actually asked for.
    try:
        other_value = measure(primary, not include_hydrogens)[0].value
    except (StructureError, ValueError) as exc:                 # noqa: BLE001
        other_value = float("nan")
        notes.append(f"もう一方の原子集合（{'重原子のみ' if include_hydrogens else '全原子'}）"
                     f"の CCM は計算できませんでした: {exc}")
    ccm_heavy = result.value if not include_hydrogens else other_value
    ccm_all = result.value if include_hydrogens else other_value

    conformer_values = []
    for cid in conf_ids:
        conformer_values.append(
            result.value if cid == primary else measure(cid, include_hydrogens)[0].value)

    # Zahrt-Denmark ensemble descriptors
    v = np.asarray(conformer_values, dtype=float)
    ccm_mean = float(v.mean()) if len(v) else float("nan")
    ccm_sd = float(v.std(ddof=0)) if len(v) > 1 else 0.0 if len(v) else float("nan")
    # With a single conformer the ensemble descriptors are still defined --
    # they just have nothing to average over.  Reporting them as NaN made the
    # CSV of a batch run silently un-analysable, so report the value itself.
    boltzmann, boltzmann_sd = (ccm_mean, 0.0) if len(v) == 1 else (float("nan"),
                                                                   float("nan"))
    if energies and len(conf_ids) > 1:
        e = np.asarray(energies, dtype=float)
        w = np.exp(-(e - e.min()) / (GAS_CONSTANT * temperature))
        w = w / w.sum()
        boltzmann = float(np.dot(w, v))
        boltzmann_sd = float(math.sqrt(max(0.0, np.dot(w, (v - boltzmann) ** 2))))
        notes.append(
            f"配座アンサンブル (n={len(conf_ids)}): 最小 {v.min():.2f}、"
            f"最大 {v.max():.2f}、平均 {ccm_mean:.2f} (±{ccm_sd:.2f})、"
            f"Boltzmann 加重平均 {boltzmann:.2f} (±{boltzmann_sd:.2f})"
            f"（{energy_source}, {temperature:.6g} K）。"
            "表示値は最安定配座のものです。CCM は配座に強く依存します。"
        )
        if v.max() - v.min() > max(1.0, 0.5 * ccm_mean):
            notes.append(
                "配座による広がりが大きいため、単一の値で分子を代表させるのは危険です。"
                "触媒ライブラリの比較には Boltzmann 加重平均 (CCM_BA) と"
                "その標準偏差 (CCM_BSD) を使ってください。")
        if len(conf_ids) < 25 and external is None:
            notes.append(
                f"配座数が {len(conf_ids)} と少なめです。アンサンブル統計"
                "（平均・標準偏差・Boltzmann 平均）は乱数種によって数十 % 動きます。"
                "定量比較には -n 50 以上を推奨します。")

    if (not include_hydrogens) and ccm_all > 0 and ccm_heavy < 0.4 * ccm_all:
        notes.append(
            f"重原子のみの値 ({ccm_heavy:.2f}) が全原子の値 ({ccm_all:.2f}) より"
            "大幅に小さくなっています。この分子のキラリティは主に水素が担っているため、"
            "「水素を含める」を有効にした値も併せて検討してください。"
        )
    if result.n_permutations >= EXHAUSTIVE_LIMIT:
        notes.append("自己同型の探索が上限に達しました。値は上界の可能性があります。")

    # CCM is by definition the minimum over *all* achiral point groups, and S1
    # is always one of them -- which is what caps it at 100/3 = 33.33.  Drop S1
    # and the number is still a perfectly good continuous symmetry measure, but
    # it is no longer the chirality measure, so do not call it one.
    group_names = {str(g).strip().upper() for g in groups}
    is_ccm = "S1" in group_names
    descriptor = "CCM" if is_ccm else "CSM(" + ",".join(groups) + ")"
    if not is_ccm:
        notes.append(
            "対象群から S1（鏡映面）を外しています。表示値は **CCM ではなく**、"
            "指定した群だけについての CSM（連続対称尺度）です。CCM は全アキラル群に"
            "ついての最小値で、S1 が必ず入るため 100/3 = 33.33 を超えません。"
            "80 や 100 という数字が出るのは、この「S1 を外した」場合だけです。")
    subset_size = 0
    if subset is not None:
        subset_size = len(result.symbols)
        descriptor = ("CCM_Chiraphore" if is_ccm
                      else "CSM_Chiraphore(" + ",".join(groups) + ")")
        notes.append(
            f"分子の一部（{subset_size} 原子）だけを対象に計算しています"
            "（Zahrt–Denmark の CCM_Chiraphore）。残りの原子は座標にも重心にも"
            "寄与しません。")
    if anion:
        descriptor = ("CCM_C2-A" if (subset is None and is_ccm)
                      else descriptor + " (anion)")
    if use_mass:
        notes.append(
            "重心を質量中心（centre of mass）に取っています"
            "（公式 CSM の --use-mass 相当）。正規化の分母もこの中心を基準にするため、"
            "既定の幾何重心で計算した値とは一致しません。")

    if not result.exact:
        notes.append(
            "置換の候補が全列挙できない規模のため、割当（Hungarian）＋軸最適化の"
            "反復探索で求めています。**得られた値は上界**（真の最小値以下には"
            "ならない＝キラリティを過小評価しない）です。厳密値が必要なら "
            "--topology bonds、または水素を除いた重原子のみでお試しください。")
    if topology == "bonds":
        notes.append(
            "置換は分子グラフの自己同型に限定しています（公式 CSM ソフトの "
            "--keep-structure 相当）。csm.ossilab.net の既定はこれより緩い"
            "「色細分化の同値類」なので、同じ座標でも本ツールの方が大きい値に"
            "なることがあります。数値を突き合わせるときは --topology classes "
            "を使ってください。")

    return Analysis(result=result, mol=best_mol, full_mol=mol3d, smiles=smiles,
                    formula=formula, source=source,
                    include_hydrogens=include_hydrogens, groups=tuple(groups),
                    ccm_heavy=ccm_heavy, ccm_all=ccm_all,
                    conformer_values=conformer_values,
                    conformer_energies=energies,
                    ccm_mean=ccm_mean, ccm_sd=ccm_sd,
                    boltzmann_mean=boltzmann, boltzmann_sd=boltzmann_sd,
                    descriptor=descriptor, exact=result.exact,
                    use_mass=use_mass, subset_size=subset_size,
                    temperature=temperature, energy_source=energy_source,
                    notes=notes)


def _conformer_energies(mol: Chem.Mol, conf_ids) -> tuple:
    """``(energies in kcal/mol, force field name)``; MMFF94, else UFF.

    MMFF94 has no parameters for boron (among others).  When it cannot handle
    a molecule the caller used to get an empty list, and "report the
    lowest-energy conformer" silently degraded to "report whichever conformer
    ETKDG emitted first" -- with a conformer spread of 23.7 to 31.2 in the
    case that exposed this, that is not a small difference.  UFF covers the
    whole periodic table, so it is a far better fallback than nothing; if even
    UFF fails, the empty list comes back and ``analyse`` says so out loud
    instead of quietly picking conformer 0.
    """
    try:
        props = AllChem.MMFFGetMoleculeProperties(mol)
        if props is not None:
            out = [float(AllChem.MMFFGetMoleculeForceField(mol, props, confId=cid)
                         .CalcEnergy()) for cid in conf_ids]
            if out and all(math.isfinite(e) for e in out):
                return out, "MMFF94"
    except Exception:                                           # noqa: BLE001
        pass
    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            out = [float(AllChem.UFFGetMoleculeForceField(mol, confId=cid)
                         .CalcEnergy()) for cid in conf_ids]
            if out and all(math.isfinite(e) for e in out):
                return out, "UFF"
    except Exception:                                           # noqa: BLE001
        pass
    return [], "なし"


def molblock_with_coords(mol: Chem.Mol, coords: np.ndarray, name: str = "") -> str:
    """Same connectivity, different coordinates - for overlaying structures."""
    out = Chem.Mol(mol)
    conf = out.GetConformer()
    for i, (x, y, z) in enumerate(coords):
        conf.SetAtomPosition(i, (float(x), float(y), float(z)))
    out.SetProp("_Name", name)
    return Chem.MolToMolBlock(out, kekulize=False)
