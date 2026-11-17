# The upstream hook targets the old 'webrtcvad' distribution and pkg_resources.
# Our supported Windows wheel exposes the same module under webrtcvad-wheels.
from PyInstaller.utils.hooks import copy_metadata
datas = copy_metadata('webrtcvad-wheels')
hiddenimports = ['_webrtcvad']
