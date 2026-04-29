"""
DIRECT MODULE EXECUTOR FOR `PYTHON -M PROMPTIFY` ACCESS.
"""

if __package__ in (None, ""):
    from promptify.main import cli
else:
    from .main import cli

if __name__ == "__main__":
    cli()
