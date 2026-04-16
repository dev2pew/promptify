"""
UNIT TESTS EVALUATING THE RELIABILITY OF THE ABSTRACT SYNTAX TREE SYMBOL EXTRACTOR.
"""

import pytest

pytest.importorskip("pygments")

from promptify.core.extractor import SymbolExtractor


def test_python_extraction():
    """TESTS AST EXTRACTION FOR PYTHON CLASSES AND FUNCTIONS."""
    code = """
class MyClass:
    def method_a(self):
        pass

def standalone_func():
    pass
"""
    extractor = SymbolExtractor(code, "test.py")
    assert "MyClass" in extractor.symbols
    assert "MyClass.method_a" in extractor.symbols
    assert "standalone_func" in extractor.symbols


def test_js_extraction():
    """TESTS AST EXTRACTION FOR JS FUNCTIONS AND CLASSES."""
    code = """
function doSomething() {
    console.log("hello");
}
class User {
    login() {}
}
"""
    extractor = SymbolExtractor(code, "test.js")
    assert "doSomething" in extractor.symbols
    assert "User" in extractor.symbols
