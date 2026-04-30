"""Module entry point for `python -m promptify`"""

if __package__ in (None, ""):
    from promptify.main import cli
else:
    from .main import cli

if __name__ == "__main__":
    cli()
