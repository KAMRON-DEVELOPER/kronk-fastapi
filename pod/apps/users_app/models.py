from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import (DateTime, Enum, ForeignKey, String, UniqueConstraint,
                        func, select, text)
from sqlalchemy import TIMESTAMP
from sqlalchemy import UUID as PG_UUID
from sqlalchemy.orm import (DeclarativeBase, Mapped, column_property,
                            mapped_column, relationship)

from utility.my_enums import FollowPolicy, FollowStatus, UserRole, UserStatus

if TYPE_CHECKING:
    from ..chats_app.models import (ChatMessageModel, ChatModel,
                                    ChatParticipantModel, GroupMessageModel,
                                    GroupModel, GroupParticipantModel)
    from ..feeds_app.models import EngagementModel, FeedModel, ReportModel
    from ..vocabularies_app.models import SentenceModel, VocabularyModel
    from ..notes_app.models import NoteModel


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    __abstract__ = True
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), default=uuid4, primary_key=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), default=func.now())
    updated_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())


class FollowModel(BaseModel):
    __tablename__ = "follow_table"
    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="uq_follower_following"),)
    follower_id: Mapped[UUID] = mapped_column(ForeignKey(column="user_table.id", ondelete="CASCADE"))
    following_id: Mapped[UUID] = mapped_column(ForeignKey(column="user_table.id", ondelete="CASCADE"))
    follow_status: Mapped[FollowStatus] = mapped_column(Enum(FollowStatus, name="follow_status"), default=FollowStatus.accepted)
    follower: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="followings", foreign_keys=[follower_id])
    following: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="followers", foreign_keys=[following_id])

    def __repr__(self):
        return "FollowModel"


class UserModel(BaseModel):
    __tablename__ = "user_table"

    name: Mapped[str] = mapped_column(String(length=64), nullable=False, index=True, unique=True)
    username: Mapped[str] = mapped_column(String(length=64), nullabel=False, index=True, unique=True)
    email: Mapped[str] = mapped_column(String(length=64), nullabel=False, index=True, unique=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True, unique=True)
    password: Mapped[str] = mapped_column(String(length=120))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    banner_color: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    birthdate: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.regular)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, name="user_status"), default=UserStatus.active)
    follow_policy: Mapped[FollowPolicy] = mapped_column(Enum(FollowPolicy, name="follow_policy"), default=FollowPolicy.auto_accept)

    followers_count: Mapped[int] = column_property(select(func.count(FollowModel.id)).where(text("following_id = id")).correlate_except(FollowModel).scalar_subquery())
    followings_count: Mapped[int] = column_property(select(func.count(FollowModel.id)).where(text("follower_id = id")).correlate_except(FollowModel).scalar_subquery())

    followers: Mapped[list["FollowModel"]] = relationship(argument="FollowModel", back_populates="following", foreign_keys="[FollowModel.following_id]",
                                                          cascade="all, delete-orphan")
    followings: Mapped[list["FollowModel"]] = relationship(argument="FollowModel", back_populates="follower", foreign_keys="[FollowModel.follower_id]",
                                                           cascade="all, delete-orphan")
    blocked_users: Mapped[list["BlockModel"]] = relationship("BlockModel", back_populates="blocker", foreign_keys="[BlockModel.blocker_id]")
    blockers: Mapped[list["BlockModel"]] = relationship("BlockModel", back_populates="blocked", foreign_keys="[BlockModel.blocked_id]")
    feeds: Mapped[list["FeedModel"]] = relationship(argument="FeedModel", back_populates="author", passive_deletes=True)
    engagements: Mapped[list["EngagementModel"]] = relationship(argument="EngagementModel", back_populates="user", passive_deletes=True)
    reports: Mapped[list["ReportModel"]] = relationship(argument="ReportModel", back_populates="user", passive_deletes=True)

    group_participants: Mapped[list["GroupParticipantModel"]] = relationship(argument="GroupParticipantModel", back_populates="user", passive_deletes=True)
    groups: Mapped[list["GroupModel"]] = relationship(secondary="group_participant_table", back_populates="users", viewonly=True)
    group_messages: Mapped[list["GroupMessageModel"]] = relationship(argument="GroupMessageModel", back_populates="sender")
    chat_participants: Mapped[list["ChatParticipantModel"]] = relationship(argument="ChatParticipantModel", back_populates="user", passive_deletes=True)
    chats: Mapped[list["ChatModel"]] = relationship(secondary="chat_participant_table", back_populates="users", viewonly=True)
    chat_messages: Mapped[list["ChatMessageModel"]] = relationship(argument="ChatMessageModel", back_populates="sender")
    # tabs: Mapped[list["TabModel"]] = relationship(back_populates="owner", cascade="all, delete-orphan", passive_deletes=True)
    vocabularies: Mapped[list["VocabularyModel"]] = relationship(secondary="user_vocabulary_table", back_populates="users", cascade="all, delete")
    sentences: Mapped[list["SentenceModel"]] = relationship(argument="SentenceModel", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True)
    notes: Mapped[list["NoteModel"]] = relationship(argument="NoteModel", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True)

    # @hybrid_property
    # def followers_count(self):
    #     return len(self.followers)

    # @hybrid_property
    # def followings_count(self):
    #     return len(self.followings)

    # @followers_count.expression
    # def followers_count(cls):  # noqa
    #     return select(func.count(FollowModel.id)).where(FollowModel.following_id == cls.id).label("followers_count")

    # @followings_count.expression
    # def followings_count(cls):  # noqa
    #     return select(func.count(FollowModel.id)).where(FollowModel.follower_id == cls.id).label("followings_count")

    def __repr__(self):
        return f"UserModel of {self.username}"


class BlockModel(BaseModel):
    __tablename__ = "block_table"

    blocker_id: Mapped[UUID] = mapped_column(ForeignKey(column="user_table.id", ondelete="CASCADE"))
    blocked_id: Mapped[UUID] = mapped_column(ForeignKey(column="user_table.id", ondelete="CASCADE"))
    blocker: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="blocked_users", foreign_keys=[blocker_id])
    blocked: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="blockers", foreign_keys=[blocked_id])

    def __repr__(self):
        return "BlockModel"
