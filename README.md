# Drone Multispectral Vegetation Indices

QGIS plugin for calculating vegetation index maps from separate Pix4D drone reflectance GeoTIFFs loaded as raster layers.

The plugin creates one georeferenced Float32 GeoTIFF per selected index:

- `NDVI`: `(NIR - Red) / (NIR + Red)`
- `NDRE`: `(NIR - RedEdge) / (NIR + RedEdge)`
- `SAVI`: `((NIR - Red) / (NIR + Red + L)) * (1 + L)`
- `MSAVI`: `(2 * NIR + 1 - sqrt((2 * NIR + 1)^2 - 8 * (NIR - Red))) / 2`
- `GNDVI`: `(NIR - Green) / (NIR + Green)`

## Usage

1. Open QGIS and enable the plugin.
2. Add the Pix4D Blue, Green, Red, Red Edge, and NIR reflectance `.tif` or `.tiff` maps to QGIS as raster layers.
3. Go to Raster > Drone Vegetation Indices > Calculate Vegetation Index Maps.
4. Select the loaded reflectance layer for each band.
5. Set the output folder.
6. Set the output filename prefix.
7. Select the indices to calculate.
8. Run the tool.

## Install in QGIS

### Install from ZIP

1. Open QGIS Desktop.
2. Go to Plugins > Manage and Install Plugins.
3. Open the Install from ZIP tab.
4. Select `plugins_drone_multispectral_images_vegetative_indices.zip`.
5. Click Install Plugin.
6. Enable the plugin if QGIS does not enable it automatically.

### Development install

Copy this plugin folder into your QGIS profile plugins folder.

On Windows, the default profile path is usually:

```text
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\plugins_drone_multispectral_images_vegetative_indices
```

Restart QGIS, then enable the plugin from Plugins > Manage and Install Plugins.

## Reflectance Map Inputs

The plugin expects separate single-band reflectance maps, such as Pix4D outputs named like:

- `*_blue.tif`
- `*_green.tif`
- `*_red.tif`
- `*_red_edge.tif`
- `*_nir.tif`

It reads band 1 from each selected raster. The rasters must have the same pixel size, row/column count, geotransform, and projection.

## Output

Outputs are named from the output prefix and index, for example:

- `field_orthomosaic_ndvi.tif`
- `field_orthomosaic_ndre.tif`
- `field_orthomosaic_savi.tif`

Each output keeps the same extent, pixel size, projection, and metadata as the selected reflectance rasters. Invalid pixels and divide-by-zero results are written as the selected NoData value.
