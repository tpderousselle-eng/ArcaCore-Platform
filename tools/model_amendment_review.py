"""Read certified parent JSON and print an unresolved amendment review packet.

Requires an explicit input path. Never imports fixture helpers or writes authority.
"""
import argparse
from pathlib import Path

from arcadev.model_approval import ApprovedDomainModel
from arcadev.model_amendment_request import ModelAmendmentRequest, model_amendment_review
from arcadev.architecture_specification import _json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path, help="Complete certified ApprovedDomainModel JSON")
    args = parser.parse_args()
    if args.parent.stat().st_size > 5_000_000:
        parser.error("Parent authority exceeds the input limit.")
    parent = ApprovedDomainModel.from_json(args.parent.read_text(encoding="utf-8"))
    print(_json(model_amendment_review(ModelAmendmentRequest.create(parent))), end="")


if __name__ == "__main__":
    main()
