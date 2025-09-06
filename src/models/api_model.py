from typing import TypeVar
from fastapi import Response, status
from pydantic import BaseModel


class AuthenticationSuccess(BaseModel):
    token: str


class AuthenticationFailure(BaseModel):
    message: str


APIErrorType = TypeVar('APIErrorType')


def api_error(error: APIErrorType, response: Response, code=status.HTTP_400_BAD_REQUEST) -> APIErrorType:
    response.status_code = code
    return error


AuthenticationResult = AuthenticationSuccess | AuthenticationFailure
