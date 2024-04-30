import datetime
import sqlalchemy
from sqlalchemy import orm
from .db_session import SqlAlchemyBase


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String)
    chat_id = sqlalchemy.Column(sqlalchemy.String, unique=True)
    created_date = sqlalchemy.Column(sqlalchemy.DateTime,
                                     default=datetime.datetime.now)
    own_words = orm.relationship('OwnWord',
                                 secondary="own_words_to_user",
                                 backref="user")
    categories_studied = orm.relationship('Category',
                                          secondary='categories_to_user')
    own_words_studied = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
