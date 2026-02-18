from pydantic import BaseModel

class ChannelOut(BaseModel):
    id: int
    username: str
    title: str | None = None
    category: str | None = None
    is_active: bool

    class Config:
        from_attributes = True

class ChannelIn(BaseModel):
    username: str