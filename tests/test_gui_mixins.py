"""The window's mixins: each method defined once, and WindowBase in step with them."""
import ast
import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ou_dedetai.gui import window  # noqa: E402
from ou_dedetai.gui.mixins import base  # noqa: E402

PARTS = [cls for cls in window.MainWindow.__mro__
         if cls is window.MainWindow or cls.__name__.endswith("Mixin")]


def declared_for_type_checking() -> tuple[set[str], set[str]]:
    """The methods and attributes WindowBase lists under TYPE_CHECKING."""
    tree = ast.parse(Path(base.__file__).read_text())
    cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
               and any(ast.unparse(b) == "GuiApp" for b in node.bases))
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    attributes = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    return methods, attributes


class TestMixins(unittest.TestCase):
    def test_every_mixin_is_in_the_window(self):
        mixins = {cls.__name__ for cls in PARTS} - {"MainWindow"}
        self.assertEqual(len(mixins), 10)

    def test_no_method_is_defined_twice(self):
        # A method in two mixins would silently hide one of them.
        seen: dict[str, str] = {}
        for cls in PARTS:
            for name, value in vars(cls).items():
                if inspect.isfunction(value):
                    self.assertNotIn(name, seen, f"{name} is in both {seen.get(name)} and {cls.__name__}")
                    seen[name] = cls.__name__

    def test_mixins_are_plain_classes(self):
        # At run time WindowBase is empty: the window itself provides everything.
        for cls in PARTS[1:]:
            self.assertEqual(cls.__bases__, (base.WindowBase,), cls.__name__)
        self.assertEqual(base.WindowBase.__bases__, (object,))
        self.assertEqual([n for n in vars(base.WindowBase) if not n.startswith("__")], [])

    def test_declared_methods_exist(self):
        methods, _ = declared_for_type_checking()
        self.assertTrue(methods)
        for name in methods:
            self.assertTrue(inspect.isfunction(getattr(window.MainWindow, name, None)), name)

    def test_declared_attributes_are_set_by_the_window(self):
        _, attributes = declared_for_type_checking()
        source = "\n".join(Path(inspect.getfile(cls)).read_text() for cls in PARTS)
        for name in attributes:
            self.assertIn(f"self.{name} =", source.replace(f"self.{name}: ", f"self.{name} = "), name)


if __name__ == "__main__":
    unittest.main()
