from pydantic import BaseModel, ConfigDict

class ChannelOut(BaseModel):
    id: int
    username: str
    title: str | None = None
    category: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class ChannelIn(BaseModel):
    username: str


class ChannelUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    is_active: bool | None = None
