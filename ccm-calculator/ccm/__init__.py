"""ccm - Continuous Chirality Measure for molecules.

Reference implementation of the folding-unfolding continuous symmetry
measure (Zabrodsky, Peleg & Avnir) as used in

  A. F. Zahrt, S. E. Denmark, "Evaluating continuous chirality measure as a
  3D descriptor in chemoinformatics applied to asymmetric catalysis",
  Tetrahedron 2019, 75, 1841-1851.
"""

from .measure import CCMResult, ccm, csm, graph_automorphisms  # noqa: F401
from .structure import Analysis, StructureError, analyse       # noqa: F401

__version__ = "1.0.0"
