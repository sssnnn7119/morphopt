"""Concrete interfaces used for SIMP density-field updates.

The shared model classes live directly in :mod:`morphopt`.  This package owns
only the density-field material interface and its updater.
"""

from .simpmaterial import SIMP_BSPFieldMaterials
from .update_simpmaterial import UpdaterSIMPMaterial

__all__ = ["SIMP_BSPFieldMaterials", "UpdaterSIMPMaterial"]
