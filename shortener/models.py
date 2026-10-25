from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    destination: Mapped[str] = mapped_column(String(2048))
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    permanent: Mapped[bool] = mapped_column(Boolean, default=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    last_clicked_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Click(Base):
    __tablename__ = "clicks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("links.code"), index=True)
    timestamp: Mapped[float] = mapped_column(Float, index=True)


class RateWindow(Base):
    __tablename__ = "rate_windows"
    principal: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
