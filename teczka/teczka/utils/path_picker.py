"""Folder selection helper backed by the native/portal file dialog.

Uses the URL-based :meth:`QFileDialog.getExistingDirectoryUrl` rather than the
string-based ``getExistingDirectory`` so that non-local locations (SFTP, SMB,
WebDAV, MTP) reachable from the desktop's file chooser can be selected at all.

On KDE and GNOME the portal/native chooser mounts the share on selection and
hands back a ``file://`` URL pointing into the mount (kio-fuse or GVfs), which
the comparison engine can use unchanged. Schemes that arrive unmounted are
reported to the caller instead of being silently mangled into an unusable path.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

# Schemes advertised to the file dialog. "file" must be present or the native
# chooser refuses to return local directories.
SUPPORTED_SCHEMES = [
    "file",
    "sftp",
    "ssh",
    "fish",
    "smb",
    "cifs",
    "dav",
    "davs",
    "webdav",
    "webdavs",
    "ftp",
    "ftps",
    "nfs",
    "mtp",
    "gphoto2",
]


def pick_folder(
    parent: Optional[QWidget],
    title: str,
    start_path: str = "",
) -> Optional[str]:
    """Ask the user for a folder and return a usable local path.

    Returns ``None`` if the user cancelled, or if they chose a remote location
    that the desktop could not present as a local mount.
    """
    dialog = QFileDialog(parent, title)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setSupportedSchemes(SUPPORTED_SCHEMES)
    if start_path:
        dialog.setDirectoryUrl(QUrl.fromLocalFile(start_path))

    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return None

    urls = dialog.selectedUrls()
    if not urls:
        return None

    url = urls[0]
    if url.isLocalFile():
        return url.toLocalFile()

    # A scheme the desktop handed back without a local mount. The comparison
    # engine speaks local paths today, so say what happened rather than
    # passing an unusable string down to the CLI.
    QMessageBox.information(
        parent,
        "Remote location not mounted",
        f"'{url.toString()}' is a {url.scheme()} location that is not "
        "available as a local mount.\n\n"
        "Open it once in your file manager so the desktop mounts it, then "
        "select it here again.",
    )
    return None
