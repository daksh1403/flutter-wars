from sqlmodel import Field, SQLModel


class Widget(SQLModel, table=True):
    __tablename__ = "widget"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=120)
    archived: bool = False
