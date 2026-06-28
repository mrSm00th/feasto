from fastapi import HTTPException, status

from app.core.auth import CurrentUser
from app.modules.users.models import User, UserRole


def require_roles(*allowed_roles: UserRole):
    """
    Dependency function to check if the current user has one of the allowed roles.
    """

    def role_checker(current_user: CurrentUser) -> User:

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )

        if not current_user.is_account_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must verify your email address to access this resource",
            )

        return current_user

    return role_checker
