from app.schemas.common import CurrentUser


class AuthService:
    def validate_user(self, current_user: CurrentUser) -> CurrentUser:
        return current_user

