import os.path
import pkgutil
from unittest import TestCase, TestSuite as UnitTestSuite

import pytest

from blueman.plugins.errors import UnsupportedPlatformError


class TestImports(TestCase):
    __test__ = False

    def __init__(self, mod_name, import_error):
        name = f"test_{mod_name.replace('.', '_')}_import"

        def f():
            try:
                __import__(mod_name)
            except (ImportError, UnsupportedPlatformError) as e:
                if import_error is None:
                    raise
                self.assertEqual(str(e), import_error)

        setattr(self, name, f)
        super().__init__(name)


def load_tests(*_args):
    expected_exceptions = {
        "blueman.main.NetworkManager": "NM python bindings not found.",
        "blueman.main.PulseAudioUtils": "Could not load pulseaudio shared library",
        "blueman.plugins.applet.GameControllerWakelock": "Only X11 platform is supported",
        "blueman.plugins.applet.KillSwitch": "Hardware kill switch not found",
        "blueman.plugins.applet.NMDUNSupport": "NM python bindings not found.",
        "blueman.plugins.applet.NMPANSupport": "NM python bindings not found.",
        "blueman.plugins.manager.PulseAudioProfile": "Could not load pulseaudio shared library",
        "blueman.plugins.mechanism.RfKill": "Hardware kill switch not found",
    }

    test_cases = UnitTestSuite()
    home = os.path.dirname(os.path.dirname(__file__))
    for package in pkgutil.walk_packages([f"{home}/blueman"], "blueman."):
        test_cases.addTest(TestImports(package.name, expected_exceptions.get(package.name)))

    assert test_cases.countTestCases() > 0

    return test_cases


@pytest.mark.filterwarnings("ignore:GLib\\.unix_signal_add_full is deprecated; use GLibUnix\\.signal_add_full instead")
def test_imports() -> None:
    load_tests().debug()
