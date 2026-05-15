"""Dialog for selecting Pix4D reflectance raster layers and vegetation index outputs."""

import os

from qgis.core import QgsMapLayerProxyModel, QgsProject
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .raster_processor import INDEX_DEFINITIONS


def _standard_button(button_box, name):
    """Return a dialog button enum for either PyQt5 or PyQt6."""
    if hasattr(button_box, "StandardButton"):
        return getattr(button_box.StandardButton, name)

    return getattr(button_box, name)


BUTTON_OK = _standard_button(QDialogButtonBox, "Ok")
BUTTON_CANCEL = _standard_button(QDialogButtonBox, "Cancel")
BUTTON_YES = _standard_button(QMessageBox, "Yes")
BUTTON_NO = _standard_button(QMessageBox, "No")


class VegetationIndicesDialog(QDialog):
    """Collect reflectance raster layers, index choices, and output options."""

    BAND_LABELS = (
        ("blue", "Blue reflectance layer"),
        ("green", "Green reflectance layer"),
        ("red", "Red reflectance layer"),
        ("red_edge", "Red Edge reflectance layer"),
        ("nir", "NIR reflectance layer"),
    )

    BAND_MATCHES = {
        "blue": ("blue", "_b"),
        "green": ("green", "_g"),
        "red": ("red", "_r"),
        "red_edge": ("red_edge", "rededge", "red edge"),
        "nir": ("nir", "near infrared"),
    }

    def __init__(self, parent=None):
        """Build the vegetation index dialog controls."""
        super().__init__(parent)
        self.setWindowTitle("Calculate Drone Vegetation Indices")
        self.resize(760, 440)

        self.layer_combo_boxes = {}
        for band_key, _ in self.BAND_LABELS:
            combo_box = QgsMapLayerComboBox(self)
            combo_box.setFilters(QgsMapLayerProxyModel.RasterLayer)
            combo_box.layerChanged.connect(self._layer_changed)
            self.layer_combo_boxes[band_key] = combo_box

        self.output_dir_edit = QLineEdit(self)
        self.output_dir_edit.setPlaceholderText("Select output folder")
        output_button = QPushButton("Browse...", self)
        output_button.clicked.connect(self._browse_output_dir)

        self.output_prefix_edit = QLineEdit(self)
        self.output_prefix_edit.setPlaceholderText("Output filename prefix")

        self.index_check_boxes = {}
        for index_name in INDEX_DEFINITIONS:
            check_box = QCheckBox(index_name, self)
            check_box.setChecked(True)
            self.index_check_boxes[index_name] = check_box

        self.savi_l_spin_box = QDoubleSpinBox(self)
        self.savi_l_spin_box.setDecimals(4)
        self.savi_l_spin_box.setRange(0.0, 1.0)
        self.savi_l_spin_box.setSingleStep(0.05)
        self.savi_l_spin_box.setValue(0.5)

        self.nodata_spin_box = QDoubleSpinBox(self)
        self.nodata_spin_box.setDecimals(4)
        self.nodata_spin_box.setRange(-1000000000.0, 1000000000.0)
        self.nodata_spin_box.setSingleStep(1.0)
        self.nodata_spin_box.setValue(-9999.0)

        self.load_outputs_check_box = QCheckBox("Load output layers", self)
        self.load_outputs_check_box.setChecked(True)

        form = QFormLayout()
        form.addRow("Output folder", self._file_row(self.output_dir_edit, output_button))
        form.addRow("Output prefix", self.output_prefix_edit)
        form.addRow("SAVI soil brightness L", self.savi_l_spin_box)
        form.addRow("NoData value", self.nodata_spin_box)
        form.addRow("", self.load_outputs_check_box)

        self.button_box = QDialogButtonBox(
            BUTTON_OK | BUTTON_CANCEL,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._reflectance_group())
        layout.addLayout(form)
        layout.addWidget(self._index_group())
        layout.addWidget(self.button_box)
        self._set_default_layers()
        self._set_default_output_dir()
        self._set_default_output_prefix()

    def input_paths(self):
        """Return source paths keyed by spectral band name."""
        paths = {}
        for band_key, combo_box in self.layer_combo_boxes.items():
            paths[band_key] = self._layer_path(combo_box.currentLayer())

        return paths

    def output_dir(self):
        """Return the selected output folder path."""
        return self.output_dir_edit.text().strip()

    def output_prefix(self):
        """Return the filename prefix for generated index maps."""
        prefix = self.output_prefix_edit.text().strip()
        if prefix:
            return prefix

        return "vegetation_index"

    def selected_indices(self):
        """Return the selected vegetation index names."""
        return [
            index_name
            for index_name, check_box in self.index_check_boxes.items()
            if check_box.isChecked()
        ]

    def savi_l(self):
        """Return the SAVI soil brightness correction factor."""
        return self.savi_l_spin_box.value()

    def nodata_value(self):
        """Return the NoData value that will replace invalid output pixels."""
        return self.nodata_spin_box.value()

    def should_load_outputs(self):
        """Return whether generated index rasters should be loaded into QGIS."""
        return self.load_outputs_check_box.isChecked()

    def accept(self):
        """Validate dialog inputs before closing with an accepted result."""
        output_dir = self.output_dir()

        if not output_dir:
            QMessageBox.warning(self, "Output required", "Select an output folder.")
            return

        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as error:
                QMessageBox.warning(
                    self,
                    "Output folder not found",
                    "The selected output folder could not be created:\n{}".format(error),
                )
                return

        selected_indices = self.selected_indices()
        if not selected_indices:
            QMessageBox.warning(self, "Index required", "Select at least one vegetation index.")
            return

        input_paths = self.input_paths()
        for band_key in self._required_band_keys(selected_indices):
            input_path = input_paths.get(band_key, "")
            if not input_path:
                QMessageBox.warning(self, "Input required", "Select the {} reflectance layer.".format(band_key))
                return

            if not os.path.isfile(input_path):
                QMessageBox.warning(self, "Input not found", "The {} layer source file does not exist.".format(band_key))
                return

            extension = os.path.splitext(input_path)[1].lower()
            if extension not in (".tif", ".tiff"):
                QMessageBox.warning(self, "Invalid input", "Select GeoTIFF layers with .tif or .tiff file sources.")
                return

        output_paths = self._output_paths(output_dir, self.output_prefix(), selected_indices)
        existing_outputs = [path for path in output_paths if os.path.exists(path)]
        if existing_outputs:
            response = QMessageBox.question(
                self,
                "Replace outputs?",
                "Some output files already exist. Replace them?",
                BUTTON_YES | BUTTON_NO,
                BUTTON_NO,
            )
            if response != BUTTON_YES:
                return

        super().accept()

    def _browse_output_dir(self):
        """Open a folder picker for generated GeoTIFF outputs."""
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self.output_dir(),
        )
        if output_dir:
            self.output_dir_edit.setText(output_dir)

    def _layer_changed(self, layer):
        """Update output defaults when selected reflectance layers change."""
        self._set_default_output_dir(force=False)
        self._set_default_output_prefix(force=False)

    def _set_default_layers(self):
        """Guess band layer selections from loaded raster layer names."""
        layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer.type() == layer.RasterLayer
        ]

        for band_key, combo_box in self.layer_combo_boxes.items():
            match = self._matching_layer(layers, band_key)
            if match is not None:
                combo_box.setLayer(match)

    def _set_default_output_dir(self, force=True):
        """Suggest an output folder based on the first selected reflectance layer."""
        if self.output_dir_edit.text().strip() and not force:
            return

        first_path = self._first_input_path()
        if first_path:
            self.output_dir_edit.setText(os.path.join(os.path.dirname(first_path), "indices"))

    def _set_default_output_prefix(self, force=True):
        """Suggest an output filename prefix from selected reflectance map names."""
        if self.output_prefix_edit.text().strip() and not force:
            return

        paths = [path for path in self.input_paths().values() if path]
        if not paths:
            return

        names = [os.path.splitext(os.path.basename(path))[0] for path in paths]
        prefix = os.path.commonprefix(names).rstrip("_- ")
        if not prefix:
            prefix = names[0]

        for suffix in ("_index", "-index", " index"):
            if prefix.lower().endswith(suffix):
                prefix = prefix[: -len(suffix)].rstrip("_- ")

        self.output_prefix_edit.setText(prefix or "vegetation_index")

    def _reflectance_group(self):
        """Create the reflectance layer selection controls."""
        group = QGroupBox("Pix4D reflectance maps", self)
        form = QFormLayout(group)
        for band_key, label in self.BAND_LABELS:
            form.addRow(label, self.layer_combo_boxes[band_key])

        return group

    def _index_group(self):
        """Create the vegetation index selection controls."""
        group = QGroupBox("Indices to calculate", self)
        grid = QGridLayout(group)
        for index, (index_name, check_box) in enumerate(self.index_check_boxes.items()):
            row = index // 3
            col = index % 3
            grid.addWidget(check_box, row, col)

        return group

    def _layer_path(self, layer):
        """Return the filesystem path for a QGIS raster layer."""
        if layer is None:
            return ""

        source = layer.source().strip()
        if "|" in source:
            source = source.split("|", 1)[0]

        return source

    def _first_input_path(self):
        """Return the first selected layer path."""
        for path in self.input_paths().values():
            if path:
                return path

        return ""

    def _required_band_keys(self, selected_indices):
        """Return band keys needed by the selected indices."""
        required = []
        for index_name in selected_indices:
            for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
                if band_key not in required:
                    required.append(band_key)

        return required

    def _output_paths(self, output_dir, output_prefix, selected_indices):
        """Return expected output paths for selected index names."""
        return [
            os.path.join(output_dir, "{}_{}.tif".format(output_prefix, index_name.lower()))
            for index_name in selected_indices
        ]

    def _matching_layer(self, layers, band_key):
        """Return a loaded raster layer whose name looks like the requested band."""
        for layer in layers:
            layer_text = "{} {}".format(layer.name(), self._layer_path(layer)).lower()
            if band_key == "red" and self._contains_red_edge(layer_text):
                continue
            if any(pattern in layer_text for pattern in self.BAND_MATCHES[band_key]):
                return layer

        return None

    def _contains_red_edge(self, text):
        """Return whether text appears to identify the red edge band."""
        return any(pattern in text for pattern in self.BAND_MATCHES["red_edge"])

    def _file_row(self, line_edit, button):
        """Create a compact row containing a path field and browse button."""
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return row
