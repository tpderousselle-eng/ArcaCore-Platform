from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    API = "api"