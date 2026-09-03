"""Canonical application definitions for Stabilization 25.1.

The definitions in this module are intentionally data only.  The golden matrix
test suite generates every application in a temporary directory through the
normal ``tools.generate`` pipeline.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenModule:
    """One module and its complete generator DSL declaration."""

    name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class GoldenApplication:
    """A representative application composed of generated modules."""

    name: str
    description: str
    modules: tuple[GoldenModule, ...]


GOLDEN_APPLICATIONS = (
    GoldenApplication(
        name="simple_crud_saas",
        description="A small SaaS task resource with common validation and indexing.",
        modules=(
            GoldenModule(
                "Task",
                (
                    "title:str:min_length=1:length=160",
                    "description:text:nullable",
                    "state:choice(Todo,Doing,Done):default='Todo'",
                    "priority:int:min=0:max=5:default=0",
                    "due_on:date:nullable",
                    "index(state,priority)",
                ),
            ),
        ),
    ),
    GoldenApplication(
        name="ecommerce_product_order",
        description="Products, orders, and line items with two parent relationships.",
        modules=(
            GoldenModule(
                "Product",
                (
                    "sku:str:min_length=1:length=64:unique",
                    "name:str:min_length=1:length=200",
                    "price:decimal(12,2):min=0",
                    "active:bool:default=True",
                ),
            ),
            GoldenModule(
                "Order",
                (
                    "reference:uuid:unique",
                    "status:choice(Draft,Paid,Shipped):default='Draft'",
                    "total:decimal(12,2):min=0",
                    "soft_delete",
                    "index(status,created_at)",
                ),
            ),
            GoldenModule(
                "Item",
                (
                    "order_id:int:fk=orders.id:one_to_many(Order,items):cascade_delete:passive_deletes",
                    "product_id:int:fk=products.id:one_to_many(Product,items)",
                    "quantity:int:min=1",
                    "unit_price:decimal(12,2):min=0",
                    "unique_together(order_id,product_id)",
                ),
            ),
        ),
    ),
    GoldenApplication(
        name="crm_customer_contact",
        description="CRM customers and contacts with normalized contact formats.",
        modules=(
            GoldenModule(
                "Customer",
                (
                    "name:str:min_length=1:length=200",
                    "industry:str:length=120:nullable",
                    "website:str:format=url:length=300:nullable",
                ),
            ),
            GoldenModule(
                "Contact",
                (
                    "customer_id:int:fk=customers.id:one_to_many(Customer,contacts):cascade_delete:passive_deletes",
                    "email:str:format=email:length=254",
                    "phone:str:format=phone:length=32:nullable",
                    "is_primary:bool:default=False",
                    "partial_index(customer_id,email,where=is_primary == True,unique=True)",
                ),
            ),
        ),
    ),
    GoldenApplication(
        name="multitenant_workspace_user",
        description="Tenant membership with workspace-scoped user uniqueness.",
        modules=(
            GoldenModule(
                "Workspace",
                (
                    "slug:str:format=slug:length=80:unique",
                    "name:str:min_length=1:length=160",
                ),
            ),
            GoldenModule(
                "User",
                (
                    "email:str:format=email:length=254:unique",
                    "display_name:str:length=160",
                ),
            ),
            GoldenModule(
                "Member",
                (
                    "workspace_id:int:fk=workspaces.id:one_to_many(Workspace,members):cascade_delete:passive_deletes",
                    "user_id:int:fk=users.id:one_to_many(User,members):cascade_delete:passive_deletes",
                    "role:choice(Owner,Admin,Member):default='Member'",
                    "unique_together(workspace_id,user_id)",
                    "index(workspace_id,role)",
                ),
            ),
        ),
    ),
    GoldenApplication(
        name="advanced_combination",
        description="Relationships composed with every advanced field and metadata family.",
        modules=(
            GoldenModule(
                "User",
                ("email:str:format=email:length=254:unique",),
            ),
            GoldenModule(
                "Role",
                ("name:str:min_length=1:length=80:unique",),
            ),
            GoldenModule(
                "Record",
                (
                    "owner_id:int:fk=users.id:one_to_many(User,records):cascade_delete:passive_deletes",
                    "roles:many_to_many(Role)",
                    "name:str:min_length=1:length=160",
                    "quantity:int:min=1",
                    "total:int:computed=quantity * 2",
                    "label:str:hybrid=name + '-advanced'",
                    "secret:text:nullable:encrypted=GOLDEN_MATRIX_KEY",
                    "email:str:format=email:length=254",
                    "status:choice(Open,Closed):default='Open'",
                    "tags:array(str):nullable",
                    "metadata_value:json:nullable",
                    "audit_fields(users.id,int)",
                    "version_column",
                    "soft_delete",
                    "index(owner_id,status)",
                    "partial_index(email,where=deleted_at is None,unique=True)",
                    "expression_index(lower(email),where=deleted_at is None,unique=True)",
                    "unique_together(owner_id,name)",
                    "check(quantity >= 1)",
                ),
            ),
        ),
    ),
)
