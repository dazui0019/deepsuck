from __future__ import annotations

from typing import Callable

import pyqtgraph as pg
from pyqtgraph import functions as fn
from PySide6 import QtCore, QtWidgets

from .constants import AXIS_COLOR, AXIS_TEXT, PANEL_BACKGROUND, TEXT_PRIMARY


def make_info_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setWordWrap(False)
    label.setStyleSheet(
        f"QLabel {{ color: {TEXT_PRIMARY}; background: {PANEL_BACKGROUND}; padding: 4px 8px; border: 1px solid #D9D2C7; font-family: Consolas, monospace; font-size: 12px; font-weight: 600; }}"
    )
    return label


class ScopeViewBox(pg.ViewBox):
    def __init__(self, reset_callback: Callable[[], None] | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_callback = reset_callback
        self.setMouseMode(pg.ViewBox.RectMode)

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            if self._reset_callback is not None:
                self._reset_callback()
            else:
                self.enableAutoRange()
                self.autoRange()
            return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev, axis=None) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()

            pos = ev.pos()
            last_pos = ev.lastPos()
            dif = (pos - last_pos) * -1

            mouse_enabled = [1.0 if enabled else 0.0 for enabled in self.state["mouseEnabled"]]
            if axis is not None:
                mouse_enabled[1 - axis] = 0.0

            tr = self.childGroup.transform()
            tr = fn.invertQTransform(tr)
            tr = tr.map(dif) - tr.map(pg.Point(0, 0))

            x = tr.x() if mouse_enabled[0] else None
            y = tr.y() if mouse_enabled[1] else None

            self._resetTarget()
            if x is not None or y is not None:
                self.translateBy(x=x, y=y)
            self.sigRangeChangedManually.emit(self.state["mouseEnabled"])
            return

        super().mouseDragEvent(ev, axis=axis)


class ScopePlotWidget(pg.PlotWidget):
    def __init__(self, reset_callback: Callable[[], None] | None = None, *args, **kwargs) -> None:
        kwargs.setdefault("viewBox", ScopeViewBox(reset_callback=reset_callback))
        super().__init__(*args, **kwargs)

    def autoRangeEnabled(self) -> tuple[bool, bool]:
        return self.plotItem.vb.autoRangeEnabled()
