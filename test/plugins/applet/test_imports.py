import os.path
import pkgutil
from unittest import TestCase, TestSuite as UnitTestSuite

from blueman.plugins.errors import UnsupportedPlatformError


class TestImports(TestCase):
    __test__ = False

    def __init__(self, mod_name, import_error):
        name = f"test_{mod_name.replace('.', '_')}_import"

        def run():
            try:
                __import__(mod_name)
            except (ImportError, UnsupportedPlatformError) as e:
                if import_error is None:
                    raise
                self.assertEqual(str(e), import_error)

        setattr(self, name, run)
        super().__init__(name)


def load_tests(*_args):
    expected_exceptions = {
        "blueman.plugins.applet.GameControllerWakelock": "Only X11 platform is supported",
        "blueman.plugins.applet.KillSwitch": "Hardware kill switch not found",
        "blueman.plugins.applet.NMDUNSupport": "NM python bindings not found.",
        "blueman.plugins.applet.NMPANSupport": "NM python bindings not found.",
    }

    test_cases = UnitTestSuite()
    home, subpath = os.path.dirname(__file__).rsplit("/test/", 1)
    for package in pkgutil.iter_modules([f"{home}/blueman/{subpath}"], f"blueman.{subpath.replace('/', '.')}."):
        test_cases.addTest(TestImports(package.name, expected_exceptions.get(package.name)))

    assert test_cases.countTestCases() > 0

    return test_cases


def test_imports() -> None:
    load_tests().debug()
