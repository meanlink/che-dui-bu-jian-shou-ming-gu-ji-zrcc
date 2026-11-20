from pydantic import BaseModel, Field, field_validator


class JobInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_id: int
    params: dict = Field(default_factory=dict)


class SupplementItem(BaseModel):
    asset: str = Field(min_length=1, max_length=80)
    lower_km: float
    upper_km: float

    @field_validator('lower_km', 'upper_km')
    @classmethod
    def finite(cls, value):
        import math
        if not math.isfinite(value):
            raise ValueError('补报里程必须是有限数值')
        return value


class SupplementInput(BaseModel):
    supplements: list[SupplementItem] = Field(min_length=1, max_length=200)
