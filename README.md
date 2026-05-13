# Drone Multispectral Vegetation Indices

QGIS plugin for calculating vegetation index maps from a drone multispectral GeoTIFF already loaded as a raster layer.

The plugin creates one georeferenced Float32 GeoTIFF per selected index:

- `NDVI`: `(NIR - Red) / (NIR + Red)`
- `NDRE`: `(NIR - RedEdge) / (NIR + RedEdge)`
- `SAVI`: `((NIR - Red) / (NIR + Red + L)) * (1 + L)`
- `MSAVI`: `(2 * NIR + 1 - sqrt((2 * NIR + 1)^2 - 8 * (NIR - Red))) / 2`
- `GNDVI`: `(NIR - Green) / (NIR + Green)`
- `VARI`: `(Green - Red) / (Green + Red - Blue)`

## Usage

1. Open QGIS and enable the plugin.
2. Add the multispectral `.tif` or `.tiff` orthomosaic to QGIS as a raster layer.
3. Go to Raster > Drone Vegetation Indices > Calculate Vegetation Index Maps.
4. Select the loaded multispectral layer.
5. Set the output folder.
6. Confirm the band mapping for Blue, Green, Red, Red Edge, and NIR.
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

## Band Mapping

Default band mapping is:

- Blue: band 1
- Green: band 2
- Red: band 3
- Red Edge: band 4
- NIR: band 5

Change these values to match the band order in your drone orthomosaic.

## Output

Outputs are named from the input raster and index, for example:

- `field_orthomosaic_ndvi.tif`
- `field_orthomosaic_ndre.tif`
- `field_orthomosaic_savi.tif`

Each output keeps the same extent, pixel size, projection, and metadata as the input raster. Invalid pixels and divide-by-zero results are written as the selected NoData value.
