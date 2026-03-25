"""Reusable context menu builders for teczka views."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QWidget


def folder_context_menu(parent: QWidget) -> QMenu:
    """Context menu for folder comparison tree items."""
    menu = QMenu(parent)
    menu.addAction(QAction("Compare Selected", parent))
    menu.addAction(QAction("Open Left", parent))
    menu.addAction(QAction("Open Right", parent))
    menu.addSeparator()
    menu.addAction(QAction("Copy to Left", parent))
    menu.addAction(QAction("Copy to Right", parent))
    menu.addSeparator()
    menu.addAction(QAction("Delete Left", parent))
    menu.addAction(QAction("Delete Right", parent))
    menu.addSeparator()
    menu.addAction(QAction("Rename...", parent))
    menu.addAction(QAction("Align...", parent))
    menu.addSeparator()
    menu.addAction(QAction("Properties", parent))
    return menu


def text_context_menu(parent: QWidget) -> QMenu:
    """Context menu for text diff views."""
    menu = QMenu(parent)
    menu.addAction(QAction("Copy Selection", parent))
    menu.addSeparator()
    menu.addAction(QAction("Copy Line to Other Side", parent))
    menu.addAction(QAction("Copy Block to Other Side", parent))
    menu.addSeparator()
    menu.addAction(QAction("Select All", parent))
    menu.addAction(QAction("Find...", parent))
    menu.addSeparator()
    menu.addAction(QAction("Toggle Edit Mode", parent))
    return menu


def hex_context_menu(parent: QWidget) -> QMenu:
    """Context menu for hex diff views."""
    menu = QMenu(parent)
    menu.addAction(QAction("Copy Hex", parent))
    menu.addAction(QAction("Copy ASCII", parent))
    menu.addSeparator()
    menu.addAction(QAction("Go to Offset...", parent))
    menu.addAction(QAction("Find...", parent))
    return menu


def image_context_menu(parent: QWidget) -> QMenu:
    """Context menu for image diff views."""
    menu = QMenu(parent)
    menu.addAction(QAction("Zoom In", parent))
    menu.addAction(QAction("Zoom Out", parent))
    menu.addAction(QAction("Fit to Window", parent))
    menu.addAction(QAction("Original Size", parent))
    menu.addSeparator()
    menu.addAction(QAction("Copy Image", parent))
    menu.addAction(QAction("Save Diff Image...", parent))
    return menu
