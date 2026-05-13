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
