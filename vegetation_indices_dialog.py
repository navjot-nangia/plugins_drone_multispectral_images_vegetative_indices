"""Dialog for selecting multispectral raster bands and vegetation index outputs."""

import os

from qgis.core import QgsMapLayerProxyModel
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
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
    """Collect loaded raster layer, band mapping, index choices, and output options."""

    BAND_LABELS = (
        ("blue", "Blue band"),
        ("green", "Green band"),
        ("red", "Red band"),
        ("red_edge", "Red Edge band"),
        ("nir", "NIR band"),
    )

    DEFAULT_BANDS = {
        "blue": 1,
        "green": 2,
        "red": 3,
        "red_edge": 4,
        "nir": 5,
    }

    def __init__(self, parent=None):
        """Build the vegetation index dialog controls."""
        super().__init__(parent)
        self.setWindowTitle("Calculate Drone Vegetation Indices")
        self.resize(700, 420)

        self.layer_combo_box = QgsMapLayerComboBox(self)
        self.layer_combo_box.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.layer_combo_box.layerChanged.connect(self._layer_changed)

        self.output_dir_edit = QLineEdit(self)
        self.output_dir_edit.setPlaceholderText("Select output folder")
        output_button = QPushButton("Browse...", self)
        output_button.clicked.connect(self._browse_output_dir)

        self.band_spin_boxes = {}
        for band_key, _ in self.BAND_LABELS:
            spin_box = QSpinBox(self)
            spin_box.setRange(1, 999)
            spin_box.setValue(self.DEFAULT_BANDS[band_key])
            self.band_spin_boxes[band_key] = spin_box

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
        form.addRow("Input multispectral layer", self.layer_combo_box)
        form.addRow("Output folder", self._file_row(self.output_dir_edit, output_button))
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
        layout.addLayout(form)
        layout.addWidget(self._band_group())
        layout.addWidget(self._index_group())
        layout.addWidget(self.button_box)
        self._set_default_output_dir()

    def input_layer(self):
        """Return the selected QGIS raster layer."""
        return self.layer_combo_box.currentLayer()

    def input_path(self):
        """Return the source path for the selected QGIS raster layer."""
        layer = self.input_layer()
        if layer is None:
            return ""

        source = layer.source().strip()
        if "|" in source:
            source = source.split("|", 1)[0]

        return source

    def output_dir(self):
        """Return the selected output folder path."""
        return self.output_dir_edit.text().strip()

    def band_map(self):
        """Return a map of spectral band names to one-based raster band numbers."""
        return {
            band_key: spin_box.value()
            for band_key, spin_box in self.band_spin_boxes.items()
        }

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
        layer = self.input_layer()
        input_path = self.input_path()
        output_dir = self.output_dir()

        if layer is None:
            QMessageBox.warning(self, "Input required", "Add a multispectral GeoTIFF layer to QGIS and select it.")
            return

        if not input_path:
            QMessageBox.warning(self, "Input required", "The selected layer does not have a readable file path.")
            return

        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "Input not found", "The selected layer source file does not exist.")
            return

        extension = os.path.splitext(input_path)[1].lower()
        if extension not in (".tif", ".tiff"):
            QMessageBox.warning(self, "Invalid input", "Select a GeoTIFF layer with a .tif or .tiff file source.")
            return

        if not output_dir:
            QMessageBox.warning(self, "Output required", "Select an output folder.")
            return

        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Output folder not found", "The selected output folder does not exist.")
            return

        selected_indices = self.selected_indices()
        if not selected_indices:
            QMessageBox.warning(self, "Index required", "Select at least one vegetation index.")
            return

        raster_band_count = layer.bandCount()
        missing_bands = []
        band_map = self.band_map()
        for index_name in selected_indices:
            for band_key in INDEX_DEFINITIONS[index_name]["bands"]:
                if band_map[band_key] > raster_band_count:
                    missing_bands.append("{} needs {} band {}".format(index_name, band_key, band_map[band_key]))

        if missing_bands:
            QMessageBox.warning(
                self,
                "Invalid band mapping",
                "The selected raster has {} band(s).\n{}".format(raster_band_count, "\n".join(missing_bands)),
            )
            return

        output_paths = self._output_paths(input_path, output_dir, selected_indices)
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
        """Update the suggested output folder when the selected raster layer changes."""
        self._set_default_output_dir(force=False)

    def _set_default_output_dir(self, force=True):
        """Suggest an output folder based on the selected raster layer."""
        if self.output_dir_edit.text().strip() and not force:
            return

        input_path = self.input_path()
        if not input_path:
            return

        self.output_dir_edit.setText(os.path.dirname(input_path))

    def _band_group(self):
        """Create the spectral band mapping controls."""
        group = QGroupBox("Band mapping", self)
        grid = QGridLayout(group)
        for row, (band_key, label) in enumerate(self.BAND_LABELS):
            grid.addWidget(QLabel(label, self), row, 0)
            grid.addWidget(self.band_spin_boxes[band_key], row, 1)

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

    def _output_paths(self, input_path, output_dir, selected_indices):
        """Return expected output paths for selected index names."""
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        return [
            os.path.join(output_dir, "{}_{}.tif".format(base_name, index_name.lower()))
            for index_name in selected_indices
        ]

    def _file_row(self, line_edit, button):
        """Create a compact row containing a path field and browse button."""
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return row
