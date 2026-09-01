from tools.core.field_parser import parse_fields

fields = parse_fields(
    [
        "title:str:length=200",
        "email:str:unique:index",
        "amount:float",
        "paid:bool:default=False",
        "customer_id:int:fk=customers.id",
        "notes:text:nullable",
    ]
)

for field in fields:
    print(field)