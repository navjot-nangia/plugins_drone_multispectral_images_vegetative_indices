"""QGIS plugin entry point for drone vegetation index map generation."""


def classFactory(iface):
    """Create the plugin instance that QGIS loads from this package."""
    from .vegetation_indices_plugin import VegetationIndicesPlugin

    return VegetationIndicesPlugin(iface)
