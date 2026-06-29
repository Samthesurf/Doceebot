from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def validate_model_output(schema: type[T], payload: object) -> T:
    return schema.model_validate(payload)
