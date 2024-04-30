import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm


class Word(SqlAlchemyBase):
    __tablename__ = 'words'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    word = sqlalchemy.Column(sqlalchemy.String)
    translation = sqlalchemy.Column(sqlalchemy.String)
    image = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    examples = sqlalchemy.Column(sqlalchemy.Text, nullable=True, default='[]')  # json
    progress = sqlalchemy.Column(sqlalchemy.Text, nullable=True, default='{}')  # json
    categories = orm.relationship("Category",
                                  secondary="words_to_category",
                                  backref="words")


own_words_to_user = sqlalchemy.Table(
    'own_words_to_user',
    SqlAlchemyBase.metadata,
    sqlalchemy.Column('users', sqlalchemy.Integer,
                      sqlalchemy.ForeignKey('users.id')),
    sqlalchemy.Column('own_words', sqlalchemy.Integer,
                      sqlalchemy.ForeignKey('own_words.id'))
)


class OwnWord(SqlAlchemyBase):
    __tablename__ = 'own_words'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.Integer)
    word = sqlalchemy.Column(sqlalchemy.String)
    translation = sqlalchemy.Column(sqlalchemy.String)
    image = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    progress = sqlalchemy.Column(sqlalchemy.Text, nullable=True, default='[null, null]')
