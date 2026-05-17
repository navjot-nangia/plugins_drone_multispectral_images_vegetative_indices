"""Raster processing helpers for calculating vegetation index GeoTIFFs."""

import math
import os


INDEX_DEFINITIONS = {
    "NDVI": {
        "bands": ("nir", "red"),
        "description": "Normalized Difference Vegetation Index",
    },
    "NDRE": {
        "bands": ("nir", "red_edge"),
        "description": "Normalized Difference Red Edge",
    },
    "SAVI": {
        "bands": ("nir", "red"),
        "description": "Soil Adjusted Vegetation Index",
    },
    "MSAVI": {
        "bands": ("nir", "red"),
        "description": "Modified Soil Adjusted Vegetation Index",
    },
    "GNDVI": {
        "bands": ("nir", "green"),
        "description": "Green Normalized Difference Vegetation Index",
    },
}

AUTO_REFLECTANCE_MAX = 1.5
COMMON_REFLECTANCE_DIVISORS = (255.0, 1000.0, 10000.0, 32768.0, 65535.0)
INTEGER_GDAL_TYPES = {"BYTE", "UINT16", "INT16", "UINT32", "INT32"}


class RasterProcessingError(RuntimeError):
    """Raised when vegetation index raster processing cannot be completed."""

    pass


def _load_raster_dependencies():
    """Import GDAL and numpy lazily from the active QGIS Python environment."""
    try:
        import numpy as np
        from osgeo import gdal
    except ImportError as error:
        raise RasterProcessingError(
            "The QGIS Python environment needs GDAL and numpy to process raster pixels."
        ) from error

    return gdal, np


def calculate_indices(
    input_paths,
    output_dir,
    output_prefix,
    indices,
    savi_l=0.5,
    output_nodata=-9999.0,
    progress_callback=None,
):
    """Write one GeoTIFF per selected vegetation index and return output paths."""
    gdal, np = _load_raster_dependencies()
    gdal.UseExceptions()

    _validate_indices(indices, input_paths)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    driver = gdal.GetDriverByName("GTiff")
    if driver is None:
        raise RasterProcessingError("The GDAL GeoTIFF driver is not available.")

    required_band_keys = _required_band_keys(indices)
    sources = _open_sources(gdal, input_paths, required_band_keys)
    reference_source = sources[required_band_keys[0]]["dataset"]
    _validate_source_alignment(sources, required_band_keys)

    x_size = reference_source.RasterXSize
    y_size = reference_source.RasterYSize
    block_x_size, block_y_size = _block_size(
        [sources[band_key]["band"] for band_key in required_band_keys],
        x_size,
        y_size,
    )
    total_blocks = int(math.ceil(x_size / block_x_size)) * int(math.ceil(y_size / block_y_size))
    total_work = total_blocks * len(indices)
    work_done = 0

    outputs = {}
    created_paths = []
    output = None

    try:
        for index_name in indices:
            output_path = _output_path(output_dir, output_prefix, index_name)
            outputs[index_name] = output_path
            if os.path.exists(output_path):
                driver.Delete(output_path)

            output = _create_output(gdal, driver, reference_source, output_path, index_name, output_nodata)
            output_band = output.GetRasterBand(1)
            created_paths.append(output_path)

            for y_offset in range(0, y_size, block_y_size):
                rows = min(block_y_size, y_size - y_offset)
                for x_offset in range(0, x_size, block_x_size):
                    cols = min(block_x_size, x_size - x_offset)
                    band_arrays, invalid_mask = _read_band_arrays(
                        sources,
                        INDEX_DEFINITIONS[index_name]["bands"],
                        x_offset,
                        y_offset,
                        cols,
                        rows,
                        np,
                    )
                    index_data = _calculate_index(index_name, band_arrays, savi_l, np)
                    index_data[invalid_mask | ~np.isfinite(index_data)] = float(output_nodata)
                    output_band.WriteArray(index_data.astype(np.float32, copy=False), x_offset, y_offset)

                    work_done += 1
                    if progress_callback and progress_callback(work_done, total_work) is False:
                        raise RasterProcessingError("Processing cancelled.")

            output_band.FlushCache()
            output.FlushCache()
            output = None

    except Exception:
        output = None
        for output_path in created_paths:
            if os.path.exists(output_path):
                driver.Delete(output_path)
        raise
    finally:
        for source in sources.values():
            source["dataset"] = None

    return outputs


def _validate_indices(indices, input_paths):
    """Validate requested indices and input path mapping."""
    if not indices:
        raise RasterProcessingError("Select at least one vegetation index.")

    for index_name in indices:
        if index_name not in INDEX_DEFINITIONS:
            raise RasterProcessingError("Unsupported vegetation index: {}".format(index_name))

        for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
            input_path = input_paths.get(band_key, "")
            if not input_path:
                raise RasterProcessingError("Missing {} reflectance raster.".format(band_key))
            if not os.path.isfile(input_path):
                raise RasterProcessingError("The {} reflectance raster does not exist.".format(band_key))


def _required_band_keys(indices):
    """Return the spectral bands needed by the selected indices."""
    required = []
    for index_name in indices:
        for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
            if band_key not in required:
                required.append(band_key)

    return required


def _open_sources(gdal, input_paths, required_band_keys):
    """Open required single-band reflectance rasters."""
    sources = {}
    for band_key in required_band_keys:
        dataset = gdal.Open(input_paths[band_key], gdal.GA_ReadOnly)
        if dataset is None:
            raise RasterProcessingError("Unable to open the {} reflectance raster.".format(band_key))

        if dataset.RasterCount < 1:
            raise RasterProcessingError("The {} reflectance raster does not contain any bands.".format(band_key))

        sources[band_key] = {
            "dataset": dataset,
            "band": dataset.GetRasterBand(1),
            "path": input_paths[band_key],
        }

    return sources


def _validate_source_alignment(sources, required_band_keys):
    """Ensure all required reflectance maps share the same grid and projection."""
    reference = sources[required_band_keys[0]]["dataset"]
    reference_projection = reference.GetProjection()
    reference_transform = reference.GetGeoTransform()
    reference_size = (reference.RasterXSize, reference.RasterYSize)

    for band_key in required_band_keys[1:]:
        dataset = sources[band_key]["dataset"]
        size = (dataset.RasterXSize, dataset.RasterYSize)
        if size != reference_size:
            raise RasterProcessingError(
                "The {} reflectance raster size does not match the other selected rasters.".format(band_key)
            )

        if dataset.GetGeoTransform() != reference_transform:
            raise RasterProcessingError(
                "The {} reflectance raster geotransform does not match the other selected rasters.".format(band_key)
            )

        if dataset.GetProjection() != reference_projection:
            raise RasterProcessingError(
                "The {} reflectance raster projection does not match the other selected rasters.".format(band_key)
            )


def _block_size(bands, x_size, y_size):
    """Return a practical processing block size for the source rasters."""
    first_band = next(iter(bands))
    block_x_size, block_y_size = first_band.GetBlockSize()
    if block_x_size <= 0:
        block_x_size = x_size
    if block_y_size <= 0:
        block_y_size = min(y_size, 256)

    return block_x_size, block_y_size


def _create_output(gdal, driver, reference_source, output_path, index_name, output_nodata):
    """Create a georeferenced single-band Float32 GeoTIFF for an index."""
    output = driver.Create(
        output_path,
        reference_source.RasterXSize,
        reference_source.RasterYSize,
        1,
        gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
    )
    if output is None:
        raise RasterProcessingError("Unable to create the {} output raster.".format(index_name))

    output.SetGeoTransform(reference_source.GetGeoTransform())
    output.SetProjection(reference_source.GetProjection())
    output.SetMetadata(reference_source.GetMetadata())

    output_band = output.GetRasterBand(1)
    output_band.SetNoDataValue(float(output_nodata))
    output_band.SetDescription("{} ({})".format(index_name, INDEX_DEFINITIONS[index_name]["description"]))
    output_band.SetMetadata({"index": index_name})
    return output


def _read_band_arrays(sources, required_bands, x_offset, y_offset, cols, rows, np):
    """Read required spectral bands and build a shared invalid-pixel mask."""
    arrays = {}
    invalid_mask = np.zeros((rows, cols), dtype=bool)

    for band_key in required_bands:
        band = sources[band_key]["band"]
        data = band.ReadAsArray(x_offset, y_offset, cols, rows)
        if data is None:
            raise RasterProcessingError("Unable to read a raster block from the {} band.".format(band_key))

        data = data.astype(np.float32, copy=False)
        invalid_mask |= ~np.isfinite(data)

        nodata = band.GetNoDataValue()
        if nodata is not None:
            if np.isnan(nodata):
                invalid_mask |= np.isnan(data)
            else:
                invalid_mask |= np.isclose(data, float(nodata))

        scale, offset = _band_scale_offset(band)
        if not _is_identity_transform(scale, offset):
            data = data * scale + offset
            invalid_mask |= ~np.isfinite(data)

        arrays[band_key] = data

    return arrays, invalid_mask


def _band_scale_offset(band):
    """Return GDAL band scale and offset values with identity defaults."""
    scale = band.GetScale()
    offset = band.GetOffset()
    if scale is None:
        scale = 1.0
    if offset is None:
        offset = 0.0

    return float(scale), float(offset)


def _is_identity_transform(scale, offset):
    """Return whether a scale/offset pair leaves pixel values unchanged."""
    return math.isclose(scale, 1.0, rel_tol=0.0, abs_tol=1e-12) and math.isclose(
        offset, 0.0, rel_tol=0.0, abs_tol=1e-12
    )


def _calculate_index(index_name, bands, savi_l, np):
    """Calculate one vegetation index from already-read source band arrays."""
    with np.errstate(divide="ignore", invalid="ignore"):
        if index_name == "NDVI":
            return _safe_divide(bands["nir"] - bands["red"], bands["nir"] + bands["red"], np)
        if index_name == "NDRE":
            return _safe_divide(bands["nir"] - bands["red_edge"], bands["nir"] + bands["red_edge"], np)
        if index_name == "SAVI":
            numerator = (bands["nir"] - bands["red"]) * (1.0 + float(savi_l))
            denominator = bands["nir"] + bands["red"] + float(savi_l)
            return _safe_divide(numerator, denominator, np)
        if index_name == "MSAVI":
            term = (2.0 * bands["nir"] + 1.0) ** 2 - 8.0 * (bands["nir"] - bands["red"])
            term = np.maximum(term, 0.0)
            return (2.0 * bands["nir"] + 1.0 - np.sqrt(term)) / 2.0
        if index_name == "GNDVI":
            return _safe_divide(bands["nir"] - bands["green"], bands["nir"] + bands["green"], np)

    raise RasterProcessingError("Unsupported vegetation index: {}".format(index_name))


def _safe_divide(numerator, denominator, np):
    """Return numerator / denominator with non-zero denominator handling."""
    result = np.full(numerator.shape, np.nan, dtype=np.float32)
    np.divide(numerator, denominator, out=result, where=denominator != 0)
    return result


def _output_path(output_dir, output_prefix, index_name):
    """Return the GeoTIFF output path for a selected index."""
    return os.path.join(output_dir, "{}_{}.tif".format(output_prefix, index_name.lower()))
