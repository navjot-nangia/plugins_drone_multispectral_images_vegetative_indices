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
    "VARI": {
        "bands": ("green", "red", "blue"),
        "description": "Visible Atmospherically Resistant Index",
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
    input_path,
    output_dir,
    indices,
    band_map,
    savi_l=0.5,
    output_nodata=-9999.0,
    progress_callback=None,
):
    """Write one GeoTIFF per selected vegetation index and return output paths."""
    gdal, np = _load_raster_dependencies()
    gdal.UseExceptions()

    source = gdal.Open(input_path, gdal.GA_ReadOnly)
    if source is None:
        raise RasterProcessingError("Unable to open the input raster.")

    if source.RasterCount < 1:
        raise RasterProcessingError("The input raster does not contain any bands.")

    _validate_indices(indices, band_map, source.RasterCount)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        raise RasterProcessingError("The output folder does not exist.")

    driver = gdal.GetDriverByName("GTiff")
    if driver is None:
        raise RasterProcessingError("The GDAL GeoTIFF driver is not available.")

    required_band_keys = _required_band_keys(indices)
    source_bands = _read_source_bands(source, band_map, required_band_keys)
    band_transforms = _source_band_transforms(source_bands, gdal)
    x_size = source.RasterXSize
    y_size = source.RasterYSize
    block_x_size, block_y_size = _block_size(source_bands.values(), x_size, y_size)
    total_blocks = int(math.ceil(x_size / block_x_size)) * int(math.ceil(y_size / block_y_size))
    total_work = total_blocks * len(indices)
    work_done = 0

    outputs = {}
    created_paths = []

    output = None
    try:
        for index_name in indices:
            output_path = _output_path(input_path, output_dir, index_name)
            outputs[index_name] = output_path
            if os.path.exists(output_path):
                driver.Delete(output_path)

            output = _create_output(gdal, driver, source, output_path, index_name, output_nodata)
            output_band = output.GetRasterBand(1)
            created_paths.append(output_path)

            for y_offset in range(0, y_size, block_y_size):
                rows = min(block_y_size, y_size - y_offset)
                for x_offset in range(0, x_size, block_x_size):
                    cols = min(block_x_size, x_size - x_offset)
                    band_arrays, invalid_mask = _read_band_arrays(
                        source_bands,
                        band_transforms,
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
        source = None
        for output_path in created_paths:
            if os.path.exists(output_path):
                driver.Delete(output_path)
        raise
    finally:
        source = None

    return outputs


def _validate_indices(indices, band_map, raster_band_count):
    """Validate requested indices and one-based band mapping."""
    if not indices:
        raise RasterProcessingError("Select at least one vegetation index.")

    for index_name in indices:
        if index_name not in INDEX_DEFINITIONS:
            raise RasterProcessingError("Unsupported vegetation index: {}".format(index_name))

        for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
            band_number = band_map.get(band_key)
            if band_number is None:
                raise RasterProcessingError("Missing band mapping for {}.".format(band_key))
            if band_number < 1 or band_number > raster_band_count:
                raise RasterProcessingError(
                    "{} needs {} band {}, but the raster has {} band(s).".format(
                        index_name,
                        band_key,
                        band_number,
                        raster_band_count,
                    )
                )


def _required_band_keys(indices):
    """Return the spectral bands needed by the selected indices."""
    required = []
    for index_name in indices:
        for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
            if band_key not in required:
                required.append(band_key)

    return required


def _read_source_bands(source, band_map, required_band_keys):
    """Return GDAL band objects keyed by spectral band name."""
    source_bands = {}
    for band_key in required_band_keys:
        band_number = band_map[band_key]
        band = source.GetRasterBand(int(band_number))
        if band is None:
            raise RasterProcessingError("Unable to read raster band {} for {}.".format(band_number, band_key))
        source_bands[band_key] = band

    return source_bands


def _source_band_transforms(source_bands, gdal):
    """Return scale/offset transforms that convert source pixels to reflectance units."""
    transforms = {}
    has_explicit_transform = False

    for band_key, band in source_bands.items():
        scale, offset = _band_scale_offset(band)
        transforms[band_key] = (scale, offset)
        has_explicit_transform = has_explicit_transform or not _is_identity_transform(scale, offset)

    if has_explicit_transform:
        return transforms

    common_scale = _infer_common_reflectance_scale(source_bands, gdal)
    if _is_identity_transform(common_scale, 0.0):
        return transforms

    return {band_key: (common_scale, 0.0) for band_key in source_bands}


def _band_scale_offset(band):
    """Return the GDAL band scale and offset, defaulting to an identity transform."""
    scale = band.GetScale()
    offset = band.GetOffset()
    if scale is None:
        scale = 1.0
    if offset is None:
        offset = 0.0

    return float(scale), float(offset)


def _is_identity_transform(scale, offset):
    """Return whether a scale/offset pair leaves pixel values unchanged."""
    return math.isclose(float(scale), 1.0) and math.isclose(float(offset), 0.0)


def _infer_common_reflectance_scale(source_bands, gdal):
    """Infer a shared scale for uncalibrated integer reflectance rasters."""
    data_type_names = set()
    max_values = []

    for band in source_bands.values():
        data_type_names.add(gdal.GetDataTypeName(band.DataType).upper())
        max_value = _band_max_value(band)
        if max_value is not None and math.isfinite(max_value):
            max_values.append(max_value)

    if not max_values or not data_type_names.intersection(INTEGER_GDAL_TYPES):
        return 1.0

    max_value = max(max_values)
    if max_value <= AUTO_REFLECTANCE_MAX:
        return 1.0

    for divisor in COMMON_REFLECTANCE_DIVISORS:
        if max_value <= divisor * AUTO_REFLECTANCE_MAX:
            return 1.0 / divisor

    return 1.0


def _band_max_value(band):
    """Return a band maximum from GDAL statistics, or None if unavailable."""
    try:
        statistics = band.GetStatistics(False, True)
    except Exception:
        statistics = None

    if statistics and len(statistics) >= 2 and statistics[1] is not None:
        return float(statistics[1])

    try:
        _, max_value = band.ComputeRasterMinMax(False)
    except Exception:
        return None

    return float(max_value)


def _block_size(bands, x_size, y_size):
    """Return a practical processing block size for the source raster."""
    first_band = next(iter(bands))
    block_x_size, block_y_size = first_band.GetBlockSize()
    if block_x_size <= 0:
        block_x_size = x_size
    if block_y_size <= 0:
        block_y_size = min(y_size, 256)

    return block_x_size, block_y_size


def _create_output(gdal, driver, source, output_path, index_name, output_nodata):
    """Create a georeferenced single-band Float32 GeoTIFF for an index."""
    output = driver.Create(
        output_path,
        source.RasterXSize,
        source.RasterYSize,
        1,
        gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
    )
    if output is None:
        raise RasterProcessingError("Unable to create the {} output raster.".format(index_name))

    output.SetGeoTransform(source.GetGeoTransform())
    output.SetProjection(source.GetProjection())
    output.SetMetadata(source.GetMetadata())

    output_band = output.GetRasterBand(1)
    output_band.SetNoDataValue(float(output_nodata))
    output_band.SetDescription("{} ({})".format(index_name, INDEX_DEFINITIONS[index_name]["description"]))
    output_band.SetMetadata({"index": index_name})
    return output


def _read_band_arrays(source_bands, band_transforms, required_bands, x_offset, y_offset, cols, rows, np):
    """Read required spectral bands and build a shared invalid-pixel mask."""
    arrays = {}
    invalid_mask = np.zeros((rows, cols), dtype=bool)

    for band_key in required_bands:
        band = source_bands[band_key]
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

        scale, offset = band_transforms[band_key]
        if not _is_identity_transform(scale, offset):
            data = data * scale + offset
            invalid_mask |= ~np.isfinite(data)

        arrays[band_key] = data

    return arrays, invalid_mask


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
        if index_name == "VARI":
            return _safe_divide(bands["green"] - bands["red"], bands["green"] + bands["red"] - bands["blue"], np)

    raise RasterProcessingError("Unsupported vegetation index: {}".format(index_name))


def _safe_divide(numerator, denominator, np):
    """Return numerator / denominator with non-zero denominator handling."""
    result = np.full(numerator.shape, np.nan, dtype=np.float32)
    np.divide(numerator, denominator, out=result, where=denominator != 0)
    return result


def _output_path(input_path, output_dir, index_name):
    """Return the GeoTIFF output path for a selected index."""
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, "{}_{}.tif".format(base_name, index_name.lower()))
