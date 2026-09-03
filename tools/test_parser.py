"""Smoke-test the current field parser contract."""

import unittest

from tools.core.field_parser import parse_fields


class ParserSmokeTest(unittest.TestCase):
    def test_basic_fields(self):
        fields = parse_fields(
            "Invoice",
            [
                "title:str:length=200",
                "email:str:unique:index",
                "amount:float",
                "paid:bool:default=False",
                "customer_id:int:fk=customers.id",
                "notes:text:nullable",
            ],
        )

        self.assertEqual(
            [field.name for field in fields],
            ["title", "email", "amount", "paid", "customer_id", "notes"],
        )
        self.assertEqual(fields[0].max_length, 200)
        self.assertTrue(fields[1].unique)
        self.assertTrue(fields[1].index)
        self.assertEqual(fields[3].default, "False")
        self.assertEqual(fields[4].foreign_key, "customers.id")
        self.assertTrue(fields[5].nullable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
