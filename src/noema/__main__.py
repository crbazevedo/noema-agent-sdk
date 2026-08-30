from __future__ import annotations

from . import __version__


def main() -> None:
    print(f"Noema Agent SDK {__version__}")
    print("Run `make demo` from the repository for an autonomous example.")


if __name__ == "__main__":
    main()
