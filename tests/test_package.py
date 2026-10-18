"""Package metadata and public surface.
"""

from importlib import metadata, resources

import seeqbox


def test_version_matches_installed_metadata():
    assert isinstance(seeqbox.__version__, str)
    assert metadata.version('seeqbox') == seeqbox.__version__


def test_license_is_mit():
    assert metadata.metadata('seeqbox')['License-Expression'] == 'MIT'


def test_requires_python_312():
    assert metadata.metadata('seeqbox')['Requires-Python'] == '>=3.12'


def test_package_is_typed():
    assert resources.files('seeqbox').joinpath('py.typed').is_file()


def test_console_script_is_registered():
    scripts = metadata.entry_points(group='console_scripts')
    (script,) = [ep for ep in scripts if ep.name == 'seeqbox']
    assert script.value == 'seeqbox.cli:main'
