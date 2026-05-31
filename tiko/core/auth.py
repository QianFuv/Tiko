"""RBAC helpers for the FastAPI control plane."""

from tiko.domain.security import Permission, Principal, Role

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    "admin": frozenset(
        {
            "observe",
            "manage_simulations",
            "manage_research",
            "manage_plugins",
            "manage_reports",
            "manage_alerts",
            "manage_datasets",
            "manage_experiments",
            "read_audit",
        }
    ),
    "researcher": frozenset(
        {
            "observe",
            "manage_research",
            "manage_plugins",
            "manage_reports",
            "manage_datasets",
            "manage_experiments",
        }
    ),
    "operator": frozenset(
        {
            "observe",
            "manage_simulations",
            "manage_reports",
            "manage_alerts",
        }
    ),
    "viewer": frozenset({"observe"}),
}


def has_permission(principal: Principal, permission: Permission) -> bool:
    """Return whether a principal has a permission.

    Args:
        principal: Current caller principal.
        permission: Required permission.

    Returns:
        Whether the caller has the permission.
    """

    return permission in ROLE_PERMISSIONS[principal.role]
