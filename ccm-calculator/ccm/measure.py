"""Continuous Symmetry Measure (CSM) / Continuous Chirality Measure (CCM).

Implements the folding-unfolding method of Zabrodsky, Peleg and Avnir
(J. Am. Chem. Soc. 1992, 114, 7843; the generalisation to arbitrary point
groups is 1993, 115, 8278, and the chirality measure itself is Zabrodsky &
Avnir, "Continuous Symmetry Measures. 4. Chirality", J. Am. Chem. Soc. 1995,
117, 462) in the normalisation used by the CSM software of the Avnir group:

    S(G) = 100 * min_{pi, T}  sum_k |Q_k - P_k|^2 / sum_k |Q_k - Q0|^2

where

    Q_k  atomic coordinates of the molecule (k = 1..N)
    Q0   centroid of {Q_k} (centre of mass if masses are supplied)
    P_k  coordinates of the *nearest* structure that possesses symmetry G
    pi   a permutation of the atoms that preserves atom type and connectivity
         (i.e. an automorphism of the molecular graph) with pi^n = identity
    T    the improper-rotation operator generating G, whose orientation is
         optimised

For a given (pi, T) the nearest symmetric structure is obtained by folding
and averaging over the group and then unfolding:

    P_k = (1/n) * sum_{i=0}^{n-1} T^{-i} Q_{pi^i(k)}

The Continuous Chirality Measure is the minimum of S over the achiral
(improper-rotation) point groups:

    CCM = min[ S(S1), S(S2), S(S4), S(S6), ... ]

S1 = Cs (a mirror plane) attains the minimum for the great majority of
organic molecules, but not for all of them: an S4-symmetric propeller is
achiral although it has neither a mirror plane nor a centre of inversion.
The reference software minimises up to S8 by default, and so does this one.

Scale: 0 (exactly achiral) to 100.

The orientation of T is solved in closed form, for every permutation, with
no numerical search -- see ``_axis_quadratic`` and ``_max_on_sphere``.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "CCMResult",
    "DEFAULT_GROUPS",
    "csm",
    "ccm",
    "graph_automorphisms",
    "element_permutations",
    "permutation_count",
    "refinement_classes",
    "refinement_permutations",
    "restrict_permutations",
    "improper_matrix",
    "reflection_matrix",
]

# The reference CSM software (Avnir group) minimises over the achiral point
# groups up to S8 by default -- and that is what the csm.ossilab.net web page
# does behind its "CCM" button, which is the tool Zahrt and Denmark used.
# S1 wins for the great majority of organic molecules, but not always: an
# S4-symmetric propeller is achiral while its best mirror plane is not, so an
# S1-only search reports it as chiral.
DEFAULT_GROUPS = ("S1", "S2", "S4", "S6", "S8")

# Above this many permutations the exhaustive search is replaced by the
# iterative assignment search (which returns an upper bound, never a value
# that is too small).
EXHAUSTIVE_LIMIT = 200_000


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------

def rotation_matrix(axis: np.ndarray, theta: float) -> np.ndarray:
    """Right-handed rotation by ``theta`` about the unit vector ``axis``."""
    u = np.asarray(axis, dtype=float)
    u = u / np.linalg.norm(u)
    ux, uy, uz = u
    K = np.array([[0.0, -uz, uy], [uz, 0.0, -ux], [-uy, ux, 0.0]])
    return np.eye(3) + math.sin(theta) * K + (1.0 - math.cos(theta)) * (K @ K)


def reflection_matrix(normal: np.ndarray) -> np.ndarray:
    """Reflection through the plane whose normal is ``normal``."""
    u = np.asarray(normal, dtype=float)
    u = u / np.linalg.norm(u)
    return np.eye(3) - 2.0 * np.outer(u, u)


def improper_matrix(axis: np.ndarray, n: int) -> np.ndarray:
    """Matrix of the improper rotation S_n about ``axis``.

    S_n = sigma_h . C_n  --  rotate by 2*pi/n about the axis, then reflect
    in the plane perpendicular to it.

    n = 1 gives a pure mirror (Cs), n = 2 gives inversion (Ci).
    """
    return reflection_matrix(axis) @ rotation_matrix(axis, 2.0 * math.pi / n)


def _operator(axis: np.ndarray, n: int) -> np.ndarray:
    """``improper_matrix`` with the two degenerate cases done exactly."""
    if n == 1:
        return reflection_matrix(axis)
    if n == 2:
        return -np.eye(3)
    return improper_matrix(axis, n)


def _centre(coords: np.ndarray, masses=None) -> np.ndarray:
    """Centroid, or centre of mass when ``masses`` is given (CSM --use-mass)."""
    Q = np.asarray(coords, dtype=float)
    if masses is None:
        return Q.mean(axis=0)
    w = np.asarray(masses, dtype=float)
    if w.shape != (len(Q),) or not np.isfinite(w).all() or w.sum() <= 0:
        raise ValueError("masses must be one positive number per atom")
    return (w[:, None] * Q).sum(axis=0) / w.sum()


# --------------------------------------------------------------------------
# permutation sources
# --------------------------------------------------------------------------

def _atom_invariant(atom) -> tuple:
    """Properties a permutation must preserve for an atom mapping."""
    return (
        atom.GetAtomicNum(),
        atom.GetFormalCharge(),
        atom.GetTotalNumHs(includeNeighbors=True),
        atom.GetDegree(),
        int(atom.GetIsAromatic()),
        int(atom.IsInRing()),
    )


def graph_automorphisms(mol, max_matches: int = EXHAUSTIVE_LIMIT) -> np.ndarray:
    """All automorphisms of the molecular graph, ignoring stereochemistry.

    Returns an (M, N) integer array; row m is a permutation ``pi`` with
    ``pi[k]`` the image of atom k.  Stereochemistry is deliberately ignored:
    the mirror image of a molecule has the same constitution, and the CSM
    permutation constraint is purely constitutional
    (``pi(i)~pi(j)`` iff ``i~j``).
    """
    matches = mol.GetSubstructMatches(
        mol, uniquify=False, useChirality=False, maxMatches=max_matches
    )
    if not matches:
        return np.arange(mol.GetNumAtoms())[None, :]

    inv = [_atom_invariant(a) for a in mol.GetAtoms()]
    bonds = {}
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        bonds[(min(i, j), max(i, j))] = b.GetBondTypeAsDouble()

    keep = []
    for m in matches:
        if any(inv[i] != inv[m[i]] for i in range(len(m))):
            continue
        ok = True
        for (i, j), order in bonds.items():
            key = (min(m[i], m[j]), max(m[i], m[j]))
            if bonds.get(key) != order:
                ok = False
                break
        if ok:
            keep.append(m)
    if not keep:
        keep = [tuple(range(mol.GetNumAtoms()))]
    return np.array(keep, dtype=int)


def permutation_count(labels: Sequence) -> float:
    """How many permutations keep every atom inside its own class.

    Returned as a float so that the factorial explosion cannot raise; it is
    only ever compared against a limit.
    """
    classes: dict = {}
    for s in labels:
        classes[s] = classes.get(s, 0) + 1
    total = 1.0
    for c in classes.values():
        total *= float(math.factorial(c))
        if total > 1e300:
            return float("inf")
    return total


def element_permutations(symbols: Sequence[str], limit: int = EXHAUSTIVE_LIMIT
                         ) -> np.ndarray:
    """Every permutation that only exchanges atoms of the same element.

    This is the "bare point set" mode used when no connectivity is known.
    It grows factorially, so it is guarded by ``limit``.
    """
    classes: dict[str, list[int]] = {}
    for i, s in enumerate(symbols):
        classes.setdefault(s, []).append(i)

    total = permutation_count(symbols)
    if total > limit:
        raise ValueError(
            f"too many element-only permutations ({total:.3g} > {limit}); "
            "supply connectivity (a mol/SDF file or SMILES) instead"
        )

    n = len(symbols)
    perms = []
    keys = list(classes)
    for combo in itertools.product(*(itertools.permutations(classes[k]) for k in keys)):
        p = np.empty(n, dtype=int)
        for k, images in zip(keys, combo):
            for src, dst in zip(classes[k], images):
                p[src] = dst
        perms.append(p)
    return np.array(perms, dtype=int)


def refinement_classes(mol) -> list:
    """Colour-refinement (1-WL) classes: the reference software's default.

    Start from ``(element, degree)`` and refine by the multiset of the
    neighbours' current classes until the partition stops changing.  Two atoms
    in the same class *may* be interchangeable; unlike a graph automorphism
    this is a necessary but not a sufficient condition, so the resulting
    permutation set is strictly larger than ``graph_automorphisms`` and can
    give a smaller (and connectivity-breaking) measure.  The Avnir CSM program
    uses exactly this partition unless ``--keep-structure`` is given.
    """
    colours = [(a.GetSymbol(), a.GetDegree()) for a in mol.GetAtoms()]
    neighbours = [[nb.GetIdx() for nb in a.GetNeighbors()] for a in mol.GetAtoms()]
    labels = {c: i for i, c in enumerate(sorted(set(colours)))}
    cur = [labels[c] for c in colours]
    for _ in range(mol.GetNumAtoms()):
        sig = [(cur[i], tuple(sorted(cur[j] for j in neighbours[i])))
               for i in range(len(cur))]
        labels = {s: i for i, s in enumerate(sorted(set(sig)))}
        new = [labels[s] for s in sig]
        if new == cur:
            break
        cur = new
    return cur


def refinement_permutations(mol, limit: int = EXHAUSTIVE_LIMIT) -> np.ndarray:
    """Every permutation that stays inside a colour-refinement class."""
    return element_permutations([str(c) for c in refinement_classes(mol)],
                                limit=limit)


def restrict_permutations(perms: np.ndarray, subset: Sequence[int]) -> np.ndarray:
    """Mappings that send ``subset`` onto itself, renumbered within it.

    Used for the chiraphore variant, where only part of the molecule is
    measured.  A permutation that moved a selected atom outside the selection
    would not be a symmetry of the sub-point-set at all, so it is dropped
    rather than truncated.  The identity always survives.
    """
    perms = np.asarray(perms, dtype=np.intp)
    if perms.ndim == 1:
        perms = perms[None, :]
    sel = np.asarray(sorted(set(int(i) for i in subset)), dtype=np.intp)
    pos = np.full(perms.shape[1], -1, dtype=np.intp)
    pos[sel] = np.arange(len(sel), dtype=np.intp)
    image = pos[perms[:, sel]]
    keep = (image >= 0).all(axis=1)
    if not keep.any():
        return np.arange(len(sel), dtype=np.intp)[None, :]
    return np.unique(image[keep], axis=0)


# --------------------------------------------------------------------------
# admissible permutations (order and cycle structure)
# --------------------------------------------------------------------------

def _perm_powers(perms: np.ndarray, n: int) -> np.ndarray:
    """``out[i][m][k] = pi_m^i(k)``, shape (n, M, N)."""
    M, N = perms.shape
    out = np.empty((n, M, N), dtype=np.intp)
    out[0] = np.broadcast_to(np.arange(N, dtype=np.intp), (M, N))
    for i in range(1, n):
        out[i] = np.take_along_axis(perms, out[i - 1], axis=1)
    return out


def _perm_order_ok(perm: np.ndarray, n: int) -> bool:
    """True if ``perm^n`` is the identity."""
    cur = perm
    for _ in range(n - 1):
        cur = perm[cur]
    return bool(np.all(cur == np.arange(len(perm))))


def _perm_cycles_ok(perm: np.ndarray, op_order: int) -> bool:
    """Cycle-structure constraint used by the reference CSM software.

    For an improper group S_n the permutation's cycles must have length
    1, ``op_order``, or 2 (the last because every S_n contains an operation
    of order 2 once n is even, and because S_1 = Cs is itself of order 2).

    This is stricter than ``perm^op_order == identity``, which would also
    admit cycles of any length dividing ``op_order``.  Dropping the extra
    permutations does not change the minimum.  Writing i = q*d + r, the fold
    over a d-cycle factorises as

        P_k = (1/p) sum_r [ sum_q T^-(qd) ] T^-r Q_{pi^r(k)},

    and ``sum_q T^-(qd)`` is (p/d) times the orthogonal projection onto the
    fixed space of ``T^d``.  For d | p with 1 < d < p and d != 2 there are
    only two cases:

      * ``T^d`` is the inversion (S6 with d = 3): its fixed space is {0}, so
        the whole orbit lands on the centroid -- the most expensive placement
        the measure allows, which cycles of length 1 also reach.
      * ``T^d`` is a proper C2 about the axis (S8 with d = 4): its fixed space
        is the axis, so the orbit lands on the axis with a *single* free
        scalar.  Splitting the same atoms into 2-cycles reaches the same axis
        with one free scalar per pair -- a strictly looser least-squares
        problem, so it can only cost less.

    Either way the restricted set attains the same minimum, and the S6/S8
    searches get markedly cheaper.  ``test_cycle_restriction_is_free``
    checks this numerically rather than taking the argument on trust.
    """
    n = len(perm)
    seen = np.zeros(n, dtype=bool)
    for start in range(n):
        if seen[start]:
            continue
        length = 0
        k = start
        while not seen[k]:
            seen[k] = True
            k = int(perm[k])
            length += 1
        if length == 1 or length == op_order or length == 2:
            continue
        return False
    return True


def _admissible(perms: np.ndarray, order: int) -> np.ndarray:
    """Vectorised ``_perm_order_ok and _perm_cycles_ok`` over a block."""
    if not len(perms):
        return perms
    N = perms.shape[1]
    ident = np.arange(N, dtype=np.intp)
    powers = _perm_powers(perms, order)                    # (order, M, N)
    closes = (np.take_along_axis(perms, powers[order - 1], axis=1) == ident).all(axis=1)
    # smallest i >= 1 with pi^i(k) == k; order if none of 1..order-1 works
    cycle_len = np.full(perms.shape, order, dtype=np.intp)
    for i in range(order - 1, 0, -1):
        cycle_len[powers[i] == ident] = i
    good = ((cycle_len == 1) | (cycle_len == 2) | (cycle_len == order)).all(axis=1)
    return perms[closes & good]


def _repair_cycles(perm: np.ndarray, order: int) -> np.ndarray:
    """Chop a free-form permutation into cycles of legal length.

    The assignment search below produces whatever mapping minimises the cost;
    it is not guaranteed to be an element of order ``order``.  Cutting each
    of its cycles into blocks of length ``order`` (then 2, then fixed points)
    keeps the pairing the assignment found while making the permutation
    admissible.  The result is only ever used as a *candidate*, and every
    candidate is scored exactly, so this can never make the answer too small.
    """
    out = np.arange(len(perm), dtype=np.intp)
    seen = np.zeros(len(perm), dtype=bool)
    for start in range(len(perm)):
        if seen[start]:
            continue
        cyc = []
        k = start
        while not seen[k]:
            seen[k] = True
            cyc.append(k)
            k = int(perm[k])
        i = 0
        while i < len(cyc):
            rest = len(cyc) - i
            take = order if rest >= order else (2 if rest >= 2 else 1)
            block = cyc[i:i + take]
            for t, a in enumerate(block):
                out[a] = block[(t + 1) % take]
            i += take
    return out


# --------------------------------------------------------------------------
# exact optimisation of the symmetry axis
# --------------------------------------------------------------------------

def _sn_coefficients(n: int):
    """cos, sin and parity of the ``p`` powers of S_n, plus ``p`` itself.

    ``T^-i = cos(th_i) (I - uu^T) - sin(th_i) [u]_x + (-1)^i uu^T`` with
    ``th_i = 2*pi*i/n``; the group has order ``p = max(n, 2)``.
    """
    p = 2 if n == 1 else n
    i = np.arange(p)
    theta = 2.0 * math.pi * (i % n) / n
    c, s = np.cos(theta), np.sin(theta)
    c[np.abs(c) < 1e-15] = 0.0                  # cos(pi) etc. exactly
    s[np.abs(s) < 1e-15] = 0.0
    return c, s, (-1.0) ** i, p


def _axis_quadratic(Q: np.ndarray, perms: np.ndarray, n: int):
    """Write ``sum_k |P_k|^2`` as ``const + u^T A u + b.u`` for each permutation.

    The folding operator ``(1/p) sum_i T^-i o pi^i`` is the average of a
    cyclic group of orthogonal operators on R^(3N), hence an *orthogonal
    projection*.  Therefore

        M = sum_k |Q_k - P_k|^2 = sum_k |Q_k|^2 - sum_k |P_k|^2,
        sum_k |P_k|^2 = <Q, P> = (1/p) sum_i tr(T^-i B_i),
        B_i = sum_k Q_{pi^i(k)} Q_k^T   (a 3x3 matrix).

    Substituting the expansion of ``T^-i`` in ``_sn_coefficients`` makes the
    trace a quadratic polynomial in the axis direction ``u``, exactly:
    ``tr(T^-i B_i) = cos(th_i) tr B_i + ((-1)^i - cos(th_i)) u^T B_i u
    - sin(th_i) u.w(B_i)`` with ``w(B) = (B23-B32, B31-B13, B12-B21)``.

    Minimising M is therefore *maximising a quadratic form on the unit
    sphere* -- no grid, no Nelder-Mead, no shortlist.  This is the analytic
    route of Pinsky, Dryzun, Casanova, Alemany & Avnir,
    J. Comput. Chem. 2008, 29, 2712.
    """
    cos_t, sin_t, parity, p = _sn_coefficients(n)
    powers = _perm_powers(perms, p)
    M = perms.shape[0]
    const = np.zeros(M)
    A = np.zeros((M, 3, 3))
    b = np.zeros((M, 3))
    for i in range(p):
        Qp = Q[powers[i]]                                   # (M, N, 3)
        B = np.matmul(Qp.transpose(0, 2, 1), Q)             # (M, 3, 3)
        if cos_t[i]:
            const += cos_t[i] * np.trace(B, axis1=1, axis2=2)
        quad = parity[i] - cos_t[i]
        if quad:
            A += quad * 0.5 * (B + B.transpose(0, 2, 1))
        if sin_t[i]:
            w = np.stack([B[:, 1, 2] - B[:, 2, 1],
                          B[:, 2, 0] - B[:, 0, 2],
                          B[:, 0, 1] - B[:, 1, 0]], axis=1)
            b -= sin_t[i] * w
    return const / p, A / p, b / p


def _max_on_sphere(A: np.ndarray, b: np.ndarray, iterations: int = 64):
    """Exact ``max_{|u|=1} u^T A u + b.u`` for a batch of symmetric 3x3 A.

    Stationarity gives ``(t I - A) u = b/2`` with multiplier ``t``; the global
    maximum is the root ``t >= lambda_max(A)`` of the secular equation
    ``sum_j beta_j^2 / (t - lambda_j)^2 = 1`` in the eigenbasis of A
    (``beta = V^T b/2``).  The function is strictly decreasing there, from
    +infinity to 0, so bisection on ``[lambda_max, lambda_max + |beta|]``
    converges to it.  When ``beta`` has no component along the top eigenspace
    the root does not exist ("hard case"): the optimum then sits at
    ``t = lambda_max`` with the deficit taken up along the top eigenvector.
    That branch is what makes S1 (where b vanishes identically) come out as
    the plain smallest-eigenvector solution.
    """
    lam, V = np.linalg.eigh(A)                       # ascending
    beta = np.einsum("mji,mj->mi", V, 0.5 * b)       # V^T (b/2)
    top = lam[:, 2]
    nb = np.linalg.norm(beta, axis=1)
    scale = np.abs(lam).max(axis=1) + nb + 1.0
    eps = 1e-13 * scale

    def secular(t):
        d = t[:, None] - lam
        return (beta * beta / np.maximum(d * d, 1e-300)).sum(axis=1)

    lo = top + eps
    hi = top + nb + eps
    hard = secular(lo) < 1.0
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        need_bigger = secular(mid) > 1.0     # still above the root -> go right
        lo = np.where(need_bigger, mid, lo)
        hi = np.where(need_bigger, hi, mid)
    t = 0.5 * (lo + hi)
    y = beta / (t[:, None] - lam)

    if hard.any():
        gap = top[:, None] - lam
        free = gap > (1e-9 * scale)[:, None]
        y_h = np.where(free, beta / np.where(free, gap, 1.0), 0.0)
        y_h[:, 2] = np.sqrt(np.maximum(0.0, 1.0 - (y_h * y_h).sum(axis=1)))
        y = np.where(hard[:, None], y_h, y)

    # A non-finite y would poison the argmin over permutations without any
    # other symptom, so fall back to the top eigenvector rather than trust it.
    bad = ~np.isfinite(y).all(axis=1)
    nrm = np.linalg.norm(y, axis=1, keepdims=True)
    bad |= (nrm[:, 0] <= 0.0)
    if bad.any():
        y = y.copy()
        y[bad] = 0.0
        y[bad, 2] = 1.0
        nrm = np.linalg.norm(y, axis=1, keepdims=True)
    y = y / nrm
    u = np.einsum("mij,mj->mi", V, y)
    value = np.einsum("mi,mij,mj->m", u, A, u) + (b * u).sum(axis=1)
    return value, u


def _solve_block(Q: np.ndarray, perms: np.ndarray, n: int):
    """``(M, axis)`` for every permutation in a block, exactly."""
    const, A, b = _axis_quadratic(Q, perms, n)
    best, u = _max_on_sphere(A, b)
    D = float((Q * Q).sum())
    return np.maximum(D - (const + best), 0.0), u


def _fold_unfold(Q: np.ndarray, perm: np.ndarray, T: np.ndarray, n: int) -> np.ndarray:
    """Nearest G-symmetric structure for a fixed permutation and operator."""
    Tinv = np.linalg.inv(T)
    P = np.zeros_like(Q)
    acc = np.eye(3)
    idx = np.arange(len(Q))
    for _ in range(n):
        P += Q[idx] @ acc.T
        acc = acc @ Tinv
        idx = perm[idx]
    return P / n


def _direction(th: float, ph: float) -> np.ndarray:
    return np.array([math.sin(th) * math.cos(ph),
                     math.sin(th) * math.sin(ph),
                     math.cos(th)])


def _fibonacci_directions(count: int) -> np.ndarray:
    """``count`` roughly equidistant directions on the sphere."""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    out = []
    for i in range(count):
        z = 1.0 - 2.0 * (i + 0.5) / count
        out.append(_direction(math.acos(max(-1.0, min(1.0, z))), golden * i))
    return np.array(out)


# --------------------------------------------------------------------------
# assignment search, for permutation sets too large to enumerate
# --------------------------------------------------------------------------

def _class_blocks(labels: Sequence) -> list:
    groups: dict = {}
    for i, c in enumerate(labels):
        groups.setdefault(c, []).append(i)
    return [np.array(v, dtype=np.intp) for v in groups.values()]


def _assign(Q: np.ndarray, T: np.ndarray, blocks: list) -> np.ndarray:
    """Cheapest atom mapping for a fixed operator, class by class.

    A structure with the symmetry satisfies ``P_{pi(k)} = T P_k``, so the
    natural candidate permutation for a trial operator is the one minimising
    ``sum_k |Q_{pi(k)} - T Q_k|^2``.  Within one equivalence class that is a
    linear assignment problem, solved exactly by the Hungarian algorithm.
    """
    from scipy.optimize import linear_sum_assignment

    TQ = Q @ T.T
    perm = np.arange(len(Q), dtype=np.intp)
    for idx in blocks:
        if len(idx) == 1:
            continue
        d = TQ[idx][:, None, :] - Q[idx][None, :, :]
        rows, cols = linear_sum_assignment((d * d).sum(axis=2))
        perm[idx[rows]] = idx[cols]
    return perm


def _assignment_search(Q: np.ndarray, labels: Sequence, n: int,
                       seeds: int = 32, max_iter: int = 12):
    """Iterate axis <-> permutation until neither changes.

    Every candidate is scored with the exact axis solver, so the value that
    comes back is attained by a real (permutation, axis) pair: it is a valid
    **upper bound** on the measure.  It is not a proof of the minimum -- that
    is what the exhaustive path gives -- but it errs on the side of calling a
    molecule *more* chiral than it is, never less.
    """
    order = 2 if n == 1 else n
    blocks = _class_blocks(labels)
    directions = list(_fibonacci_directions(seeds))
    inertia = np.linalg.eigh(Q.T @ Q)[1].T          # principal axes as seeds
    directions.extend(list(inertia))

    # Seed with the identity.  It is always admissible, and for S1 it caps the
    # measure at 100/3 (with pi = identity the fold is the projection onto the
    # mirror plane, so M = lambda_min(sum_k Q_k Q_k^T) <= tr/3).  The Hungarian
    # matching is not guaranteed to propose it, and without it this path could
    # return an "upper bound" above a ceiling the exhaustive path can never
    # exceed.
    identity = np.arange(len(Q), dtype=np.intp)
    seed_value, seed_axis = _solve_block(Q, identity[None, :], n)
    best = (float(seed_value[0]), identity, seed_axis[0])
    evaluated = 1
    seen: set = {identity.tobytes()}
    for u0 in directions:
        u = np.asarray(u0, dtype=float)
        u = u / np.linalg.norm(u)
        previous = None
        for _ in range(max_iter):
            perm = _repair_cycles(_assign(Q, _operator(u, n), blocks), order)
            key = perm.tobytes()
            if previous is not None and np.array_equal(perm, previous):
                break
            previous = perm
            if key in seen:
                break
            seen.add(key)
            values, axes = _solve_block(Q, perm[None, :], n)
            evaluated += 1
            if values[0] < best[0]:
                best = (float(values[0]), perm, axes[0])
            u = axes[0]
    return best, evaluated


# --------------------------------------------------------------------------
# the measure itself
# --------------------------------------------------------------------------

@dataclass
class CCMResult:
    value: float                      # the measure, 0-100
    group: str                        # group that attained the minimum
    coords: np.ndarray                # input coordinates (centred)
    achiral_coords: np.ndarray        # nearest achiral structure
    symbols: list[str]
    per_atom: np.ndarray              # |Q_k - P_k|^2, normalised to sum to `value`
    permutation: np.ndarray
    axis: np.ndarray                  # mirror-plane normal / S_n axis
    n_permutations: int
    per_group: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    exact: bool = True                # False when the assignment search was used

    @property
    def rmsd(self) -> float:
        """Root-mean-square displacement to the nearest achiral structure (A)."""
        d = self.coords - self.achiral_coords
        return float(np.sqrt((d * d).sum() / len(self.coords)))

    def to_xyz(self, which: str = "input", comment: str = "") -> str:
        xyz = self.coords if which == "input" else self.achiral_coords
        lines = [str(len(self.symbols)), comment or which]
        for s, (x, y, z) in zip(self.symbols, xyz):
            lines.append(f"{s:<3s} {x:12.6f} {y:12.6f} {z:12.6f}")
        return "\n".join(lines) + "\n"


def csm(coords: np.ndarray,
        symbols: Sequence[str],
        perms: np.ndarray = None,
        group: str = "S1",
        masses=None,
        classes: Sequence = None,
        chunk_cells: int = 6_000_000):
    """Continuous symmetry measure for one improper group.

    Returns ``(value, permutation, axis, nearest_symmetric_coords)``.
    """
    return _csm(coords, symbols, perms, group, masses, classes, chunk_cells)[:4]


def _csm(coords: np.ndarray,
         symbols: Sequence[str],
         perms: np.ndarray = None,
         group: str = "S1",
         masses=None,
         classes: Sequence = None,
         chunk_cells: int = 6_000_000):
    """``csm`` plus a flag saying whether the search was exhaustive.

    ``perms`` is the (M, N) array of admissible atom mappings.  Pass ``None``
    together with ``classes`` (one label per atom) to use the iterative
    assignment search instead, for permutation sets too large to enumerate;
    the value is then an upper bound and ``exact`` comes back ``False``.
    """
    Q = np.asarray(coords, dtype=float)
    Q = Q - _centre(Q, masses)
    D = float((Q * Q).sum())
    n = int(group[1:])
    if n != 1 and n % 2 != 0:
        raise ValueError("only S1 and even-order S_n groups are achiral groups")
    order = 2 if n == 1 else n

    if D <= 1e-12:
        ident = np.arange(len(Q), dtype=np.intp)
        return 0.0, ident, np.array([0.0, 0.0, 1.0]), Q.copy(), True

    if perms is None:
        if classes is None:
            raise ValueError("csm needs either `perms` or `classes`")
        (M, perm, axis), _ = _assignment_search(Q, classes, n)
        exact = False
    else:
        perms = np.asarray(perms, dtype=np.intp)
        if perms.ndim == 1:
            perms = perms[None, :]
        exact = True
        rows = max(1, int(chunk_cells // max(1, len(Q) * order)))
        M, perm, axis = np.inf, None, None
        for lo in range(0, len(perms), rows):
            block = _admissible(perms[lo:lo + rows], order)
            if not len(block):
                continue
            values, axes = _solve_block(Q, block, n)
            j = int(np.argmin(values))
            if values[j] < M:
                M, perm, axis = float(values[j]), block[j], axes[j]
        if perm is None:
            raise ValueError(f"no permutation of admissible order for group {group}")

    P = _fold_unfold(Q, perm, _operator(axis, n), order)
    d = Q - P
    value = 100.0 * float((d * d).sum()) / D
    return value, perm, axis, P, exact


def ccm(coords: np.ndarray,
        symbols: Sequence[str],
        perms: np.ndarray = None,
        groups: Iterable[str] = DEFAULT_GROUPS,
        masses=None,
        classes: Sequence = None) -> CCMResult:
    """Continuous chirality measure = min over the achiral groups given."""
    Q = np.asarray(coords, dtype=float)
    Q = Q - _centre(Q, masses)
    D = float((Q * Q).sum())

    per_group: dict[str, float] = {}
    best = None
    exact_all = True
    for g in groups:
        value, perm, axis, P, exact = _csm(Q, symbols, perms, g,
                                           masses=masses, classes=classes)
        per_group[g] = value
        exact_all = exact_all and exact
        if best is None or value < best[0]:
            best = (value, g, perm, axis, P)
        if value <= 1e-12:                 # already exactly achiral; stop early
            break

    value, group, perm, axis, P = best
    d = Q - P
    per_atom = 100.0 * (d * d).sum(axis=1) / D if D > 0 else np.zeros(len(Q))
    return CCMResult(
        value=value,
        group=group,
        coords=Q,
        achiral_coords=P,
        symbols=list(symbols),
        per_atom=per_atom,
        permutation=np.asarray(perm),
        axis=np.asarray(axis, dtype=float),
        n_permutations=(len(perms) if perms is not None else 0),
        per_group=per_group,
        exact=exact_all,
    )
