from typing import List

from rick_db import Repository
from rick_db.sql import Literal, Select, Sql

from .dto import *


class UserRepository(Repository):

    def __init__(self, conn):
        super().__init__(conn, UserRecord)

    def get_random_ids(self, limit):
        qry = self.select(cols=[UserRecord.id]).order(Literal('random()')).limit(limit)
        return self.fetch(qry)

    def get_user(self, id) -> List[GetUserRecord]:
        lateral = (
            Select(self._dialect)
            .from_({ReviewRecord: "review"}, cols=[{ReviewRecord.id: 'review_id'}, {ReviewRecord.body: 'review_body'},
                                                   {ReviewRecord.rating: 'review_rating'}])
            .join_inner({MovieRecord: "movie"}, MovieRecord.id, "review", ReviewRecord.movie_id,
                        cols=[{MovieRecord.id: 'movie_id'}, {MovieRecord.image: 'movie_image'},
                              {MovieRecord.title: 'movie_title'}, {Literal("avg_rating(movie)"): 'movie_avg_rating'}])
            .where(Literal(ReviewRecord.author_id + '= users.' + UserRecord.id))
            .order(ReviewRecord.creation_time, Sql.SQL_DESC)
            .limit(10)
        )

        qry = (
            Select(self._dialect)
            .from_(UserRecord, cols=[UserRecord.id, UserRecord.name, UserRecord.image])
            .lateral(lateral, 'q', cols=['movie_id', 'movie_image', 'movie_title', 'movie_avg_rating'])
            .where(UserRecord.id, '=', id)
        )
        return self.fetch(qry, cls=GetUserRecord)


class MovieRepository(Repository):

    def __init__(self, conn):
        super().__init__(conn, MovieRecord)

    def get_random_ids(self, limit):
        qry = self.select(cols=[MovieRecord.id]).order(Literal('random()')).limit(limit)
        return self.fetch(qry)


class PersonRepository(Repository):

    def __init__(self, conn):
        super().__init__(conn, PersonRecord)

    def get_random_ids(self, limit):
        qry = self.select(cols=[PersonRecord.id]).order(Literal('random()')).limit(limit)
        return self.fetch(qry)


class DirectorRepository(Repository):

    def __init__(self, conn):
        super().__init__(conn, DirectorRecord)

    def get_directors(self, id_movie):
        qry = (
            self.select()
            .join_inner(PersonRecord, PersonRecord.id, '=', DirectorRecord, DirectorRecord.person_id, cols=[PersonRecord.id, {Literal('persons.full_name'):'full_name'}, PersonRecord.image])
            .where(DirectorRecord.movie_id,'=', id_movie)
            .order([DirectorRecord.list_order, PersonRecord.last_name])
        )
        return self.fetch(qry)


class ReviewRepository(Repository):

    def __init__(self, conn):
        super().__init__(conn, ReviewRecord)
