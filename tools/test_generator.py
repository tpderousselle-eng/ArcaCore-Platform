from tools.generate import generate_module


def run_test(
    name: str,
    fields: list[str],
):

    print(f"Testing {name}...")

    generate_module(
        name,
        fields,
    )

    print("✓ Passed")
    print()


def main():

    run_test(
        "Invoice",
        [
            "title:str:length=200",
            "amount:float",
            "paid:bool:default=False",
        ],
    )

    run_test(
        "Customer",
        [
            "email:str:unique",
            "name:str:length=100",
        ],
    )

    run_test(
        "User",
        [
            "identifier:uuid:pk",
            "email:str:unique",
        ],
    )

    print("=" * 60)
    print("All generator smoke tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    main()