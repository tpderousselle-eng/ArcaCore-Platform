import sys

from tools.generate import generate_module


def print_help():

    print()
    print("ArcaCore")
    print("=" * 40)
    print()

    print("Commands")
    print()

    print("  generate")
    print("      Generate a new module")
    print()

    print("Examples")
    print()

    print(
        "  python -m tools generate "
        "Invoice title:str amount:float"
    )
    print()


def main():

    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == "generate":

        if len(sys.argv) < 3:
            print(
                "Missing module name."
            )
            return

        generate_module(
            sys.argv[2],
            sys.argv[3:],
        )

        return

    print(
        f"Unknown command: {command}"
    )
    print_help()


if __name__ == "__main__":
    main()