"""QGIS integration for calculating drone multispectral vegetation index maps."""

import os

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QAction, QApplication, QMessageBox, QProgressDialog
from qgis.core import Qgis, QgsProject, QgsRasterLayer

from .raster_processor import RasterProcessingError, calculate_indices
from .vegetation_indices_dialog import VegetationIndicesDialog


def _dialog_result(dialog):
    """Run a dialog with the available PyQt exec method."""
    if hasattr(dialog, "exec"):
        return dialog.exec()

    return dialog.exec_()


def _qt_window_modal():
    """Return the Qt window-modal enum for either PyQt5 or PyQt6."""
    if hasattr(Qt, "WindowModality"):
        return Qt.WindowModality.WindowModal

    return Qt.WindowModal


def _qt_wait_cursor():
    """Return the Qt wait-cursor enum for either PyQt5 or PyQt6."""
    if hasattr(Qt, "CursorShape"):
        return Qt.CursorShape.WaitCursor

    return Qt.WaitCursor


class VegetationIndicesPlugin:
    """Register the vegetation index action and run the processing workflow."""

    def __init__(self, iface):
        """Store the QGIS interface and initialize plugin action state."""
        self.iface = iface
        self.action = None
        self.menu_name = self.tr("&Drone Vegetation Indices")

    def tr(self, message):
        """Translate a plugin UI string using QGIS translation support."""
        return QCoreApplication.translate("VegetationIndicesPlugin", message)

    def initGui(self):
        """Add the plugin action to the QGIS Raster menu and toolbar."""
        self.action = QAction(self.tr("Calculate Vegetation Index Maps"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToRasterMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Remove plugin actions from the QGIS interface during unload."""
        if self.action is None:
            return

        self.iface.removePluginRasterMenu(self.menu_name, self.action)
        self.iface.removeToolBarIcon(self.action)
        self.action = None

    def run(self):
        """Collect user inputs, calculate selected indices, and optionally load outputs."""
        dialog = VegetationIndicesDialog(self.iface.mainWindow())
        if not _dialog_result(dialog):
            return

        input_paths = dialog.input_paths()
        output_dir = dialog.output_dir()
        output_prefix = dialog.output_prefix()
        selected_indices = dialog.selected_indices()
        savi_l = dialog.savi_l()
        nodata_value = dialog.nodata_value()

        progress = QProgressDialog(
            self.tr("Calculating vegetation index maps..."),
            self.tr("Cancel"),
            0,
            100,
            self.iface.mainWindow(),
        )
        progress.setWindowTitle(self.tr("Drone Vegetation Indices"))
        progress.setWindowModality(_qt_window_modal())
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def update_progress(work_done, total_work):
            """Update the progress dialog and report whether processing should continue."""
            percent = int((work_done / max(total_work, 1)) * 100)
            progress.setValue(percent)
            QApplication.processEvents()
            return not progress.wasCanceled()

        QApplication.setOverrideCursor(_qt_wait_cursor())
        try:
            outputs = calculate_indices(
                input_paths=input_paths,
                output_dir=output_dir,
                output_prefix=output_prefix,
                indices=selected_indices,
                savi_l=savi_l,
                output_nodata=nodata_value,
                progress_callback=update_progress,
            )
        except RasterProcessingError as error:
            QMessageBox.warning(self.iface.mainWindow(), self.tr("Drone Vegetation Indices"), str(error))
            return
        except Exception as error:
            QMessageBox.critical(
                self.iface.mainWindow(),
                self.tr("Drone Vegetation Indices"),
                self.tr("Unable to create vegetation index rasters:\n{}").format(error),
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

        if dialog.should_load_outputs():
            self._load_outputs(outputs)

        self.iface.messageBar().pushMessage(
            self.tr("Drone Vegetation Indices"),
            self.tr("Created {} index map(s) in {}").format(len(outputs), output_dir),
            level=Qgis.Success,
            duration=8,
        )

    def _load_outputs(self, outputs):
        """Load generated raster outputs into the current QGIS project."""
        for index_name, output_path in outputs.items():
            layer_name = "{} - {}".format(os.path.splitext(os.path.basename(output_path))[0], index_name)
            layer = QgsRasterLayer(output_path, layer_name)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
            else:
                self.iface.messageBar().pushMessage(
                    self.tr("Drone Vegetation Indices"),
                    self.tr("The {} output was written, but QGIS could not load it.").format(index_name),
                    level=Qgis.Warning,
                    duration=8,
                )
