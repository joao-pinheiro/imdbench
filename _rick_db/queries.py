#
# Copyright (c) 2019 MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##

import json
import random
import typing
from decimal import Decimal

from rick_db import fieldmapper
from rick_db.backend.pg import PgConnection
from rick_db.repository import Repository
from rick_db.sql import select, insert, update, delete, sql_with
from rick_db.sql.common import Literal as L

# Define Record classes for our models
@fieldmapper(tablename="persons", pk="id")
class Person:
    id="id"
    first_name="first_name"
    middle_name="middle_name"
    last_name="last_name"
    image="image"
    bio="b"
    
    @property
    def full_name(self) -> str:
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"

@fieldmapper(tablename="movies", pk="id")
class Movie:
    id="id"
    title="title"
    image="image"
    description="description"
    year="year"
    
    @property
    def avg_rating(self) -> float:
        return 0.0  # Will be populated by SQL directly

@fieldmapper(tablename="users", pk="id")
class User:
    id="id"
    name="name"
    image="image"

@fieldmapper(tablename="reviews", pk="id")
class Review:
    id="id"
    body="body"
    rating="rating"
    creation_time="creation_time"
    author_id="author_id"
    movie_id="movie_id"

# Define Directors and Actors join tables
@fieldmapper(tablename="directors", pk="id")
class Director:
    id="id"
    person_id="person_id"
    movie_id="movie_id"
    list_order="list_order"

@fieldmapper(tablename="actors", pk="id")
class Actor:
    id="id"
    person_id="person_id"
    movie_id="movie_id"
    list_order="list_order"

ASYNC = False
INSERT_PREFIX = 'insert_test__'

# Connection function
def connect(ctx):
    # Configure connection to match database used by other benchmarks
    conn = PgConnection(
        host=ctx.db_host,
        port=ctx.pg_port,
        dbname="postgres_bench",
        user="postgres_bench",
        password="edgedbbenchmark"
    )
    return conn

def close(ctx, conn):
    conn.close()

def load_ids(ctx, conn):
    """
    Load random IDs from the database for use in the benchmark tests.
    Uses rick_db's query builder to create the SELECT queries.
    """
    # Create random order queries with rick_db's query builder
    user_query = select.Select().from_("users", "u").order(L("RANDOM()")).limit(ctx.number_of_ids)
    movie_query = select.Select().from_("movies", "m").order(L("RANDOM()")).limit(ctx.number_of_ids)
    person_query = select.Select().from_("persons", "p").order(L("RANDOM()")).limit(ctx.number_of_ids)
    
    # Execute the queries
    users = conn.cursor().exec(user_query.query(), user_query.values())
    movies = conn.cursor().exec(movie_query.query(), movie_query.values())
    people = conn.cursor().exec(person_query.query(), person_query.values())
    
    return dict(
        get_user=[u["id"] for u in users],
        get_movie=[m["id"] for m in movies],
        get_person=[p["id"] for p in people],
        update_movie=[m["id"] for m in movies],
        insert_user=[INSERT_PREFIX] * ctx.concurrency,
        insert_movie=[{
            'prefix': INSERT_PREFIX,
            'people': [p["id"] for p in people[:4]],
        }] * ctx.concurrency,
        insert_movie_plus=[INSERT_PREFIX] * ctx.concurrency,
    )

def get_user(conn, id):
    """
    Get a user with their 10 most recent reviews.
    Uses a hybrid approach with rick_db's query builder for the main query
    and lateral join for the related data.
    """
    # For complex queries like this with LATERAL joins, we use the rick_db's
    # query builder but with some raw SQL expressions for optimized query
    # structure where needed
    
    # Create the lateral subquery for reviews
    review_subquery = select.Select() \
        .fields(['review.id AS review_id',
                 'review.body AS review_body',
                 'review.rating AS review_rating',
                 'movie.id AS movie_id',
                 'movie.image AS movie_image',
                 'movie.title AS movie_title',
                 'movie.avg_rating AS movie_avg_rating']) \
        .from_('reviews', 'review') \
        .join_inner('movies', 'movie', 'review.movie_id', 'movie.id') \
        .where('review.author_id', '=', L('users.id')) \
        .order(Review.creation_time, 'DESC') \
        .limit(10)
    
    # Build the main query with a LATERAL join
    user_query = select.Select() \
        .fields(['users.id', 'users.name', 'users.image']) \
        .from_('users') \
        .join_left_lateral(review_subquery, 'q', L('TRUE')) \
        .where('users.id', '=', id)
    
    # Execute the query
    rows = conn.cursor().exec(user_query.query(), user_query.values())
    
    if not rows:
        return json.dumps({})
    
    # Format the response
    return json.dumps({
        'id': rows[0]['id'],
        'name': rows[0]['name'],
        'image': rows[0]['image'],
        'latest_reviews': [
            {
                'id': r['q_review_id'],
                'body': r['q_review_body'],
                'rating': r['q_review_rating'],
                'movie': {
                    'id': r['q_movie_id'],
                    'image': r['q_movie_image'],
                    'title': r['q_movie_title'],
                    'avg_rating': float(r['q_movie_avg_rating']) if r['q_movie_avg_rating'] is not None else 0.0,
                }
            } for r in rows if 'q_review_id' in r and r['q_review_id'] is not None
        ]
    })

def get_movie(conn, id):
    """
    Get a movie with its directors, cast, and reviews.
    This query is complex with multiple array_agg operations and nested ROW() expressions.
    We'll use a hybrid approach with rick_db's query builder features where possible.
    """
    # This query uses a mix of rick_db query builder and SQL functions
    # We use CTEs (WITH clauses) to structure complex subqueries
    
    # Directors subquery
    directors_query = select.Select() \
        .fields([L("ROW(person.id, person.full_name, person.image) AS v")]) \
        .from_("directors") \
        .join_inner("persons", "person", "directors.person_id", "person.id") \
        .where("directors.movie_id", "=", L("movies.id")) \
        .order(L("directors.list_order NULLS LAST, person.last_name"))
    
    # Actors subquery
    actors_query = select.Select() \
        .fields([L("ROW(person.id, person.full_name, person.image) AS v")]) \
        .from_("actors") \
        .join_inner("persons", "person", "actors.person_id", "person.id") \
        .where("actors.movie_id", "=", L("movies.id")) \
        .order(L("actors.list_order NULLS LAST, person.last_name"))
    
    # Reviews subquery with nested author subquery
    reviews_query = select.Select() \
        .fields([L("""ROW(
            review.id,
            review.body,
            review.rating,
            (SELECT ROW(author.id, author.name, author.image)
             FROM users AS author
             WHERE review.author_id = author.id)
        ) AS v""")]) \
        .from_("reviews", "review") \
        .where("review.movie_id", "=", L("movies.id")) \
        .order(Review.creation_time, "DESC")
    
    # Main movie query using rick_db's query builder
    movie_query = select.Select() \
        .fields([
            'movie.id', 
            'movie.image', 
            'movie.title', 
            'movie.year', 
            'movie.description',
            'movie.avg_rating',
            L(f"""(SELECT COALESCE(array_agg(q.v), (ARRAY[])::record[]) 
                FROM ({directors_query.query()}) AS q) AS directors"""),
            L(f"""(SELECT COALESCE(array_agg(q.v), (ARRAY[])::record[]) 
                FROM ({actors_query.query()}) AS q) AS actors"""),
            L(f"""(SELECT COALESCE(array_agg(q.v), (ARRAY[])::record[]) 
                FROM ({reviews_query.query()}) AS q) AS reviews""")
        ]) \
        .from_("movies", "movie") \
        .where("movie.id", "=", id)
    
    # Execute the query
    movie = conn.cursor().fetchone(movie_query.query(), movie_query.values())
    
    if not movie:
        return json.dumps({})
    
    # Format the response
    return json.dumps({
        'id': movie['id'],
        'image': movie['image'],
        'title': movie['title'],
        'year': movie['year'],
        'description': movie['description'],
        'avg_rating': float(movie['avg_rating']) if movie['avg_rating'] is not None else 0.0,

        'directors': [
            {
                'id': d[0],
                'full_name': d[1],
                'image': d[2],
            } for d in movie['directors']
        ] if movie['directors'] else [],

        'cast': [
            {
                'id': c[0],
                'full_name': c[1],
                'image': c[2],
            } for c in movie['actors']
        ] if movie['actors'] else [],

        'reviews': [
            {
                'id': r[0],
                'body': r[1],
                'rating': r[2],
                'author': {
                    'id': r[3][0],
                    'name': r[3][1],
                    'image': r[3][2],
                }
            } for r in movie['reviews']
        ] if movie['reviews'] else []
    })

def get_person(conn, id):
    """
    Get a person with the movies they acted in and directed.
    Uses rick_db's query builder with subqueries for related data.
    """
    # Similar approach to get_movie, using CTEs for related data
    
    # Movies acted in subquery
    acted_in_query = select.Select() \
        .fields([L("ROW(movie.id, movie.image, movie.title, movie.year, movie.avg_rating) AS v")]) \
        .from_("actors") \
        .join_inner("movies", "movie", "actors.movie_id", "movie.id") \
        .where("actors.person_id", "=", L("person.id")) \
        .order(L("movie.year ASC, movie.title ASC"))
    
    # Movies directed subquery
    directed_query = select.Select() \
        .fields([L("ROW(movie.id, movie.image, movie.title, movie.year, movie.avg_rating) AS v")]) \
        .from_("directors") \
        .join_inner("movies", "movie", "directors.movie_id", "movie.id") \
        .where("directors.person_id", "=", L("person.id")) \
        .order(L("movie.year ASC, movie.title ASC"))
    
    # Main person query
    person_query = select.Select() \
        .fields([
            'person.id',
            'person.full_name',
            'person.image',
            'person.bio',
            L(f"""(SELECT COALESCE(array_agg(q.v), (ARRAY[])::record[]) 
                FROM ({acted_in_query.query()}) AS q) AS acted_in"""),
            L(f"""(SELECT COALESCE(array_agg(q.v), (ARRAY[])::record[]) 
                FROM ({directed_query.query()}) AS q) AS directed""")
        ]) \
        .from_("persons", "person") \
        .where("person.id", "=", id)
    
    # Execute the query
    person = conn.cursor().fetchone(person_query.query(), person_query.values())
    
    if not person:
        return json.dumps({})
    
    # Format the response
    return json.dumps({
        'id': person['id'],
        'full_name': person['full_name'],
        'image': person['image'],
        'bio': person['bio'],

        'acted_in': [
            {
                'id': mov[0],
                'image': mov[1],
                'title': mov[2],
                'year': mov[3],
                'avg_rating': float(mov[4]) if mov[4] is not None else 0.0,
            } for mov in person['acted_in']
        ] if person['acted_in'] else [],

        'directed': [
            {
                'id': mov[0],
                'image': mov[1],
                'title': mov[2],
                'year': mov[3],
                'avg_rating': float(mov[4]) if mov[4] is not None else 0.0,
            } for mov in person['directed']
        ] if person['directed'] else []
    })

def update_movie(conn, id):
    """
    Update a movie's title and return the updated record.
    Uses rick_db's update query builder.
    """
    # Create suffix for the movie title
    suffix = f'---{str(id)[:8]}'
    
    # Using rick_db's Update builder
    with conn.transaction():
        update_query = update.Update() \
            .table("movies") \
            .set({"title": L("movies.title || %s")}) \
            .where("id", "=", id) \
            .returning(["id", "title"])
        
        # We need to append the parameter for the concatenation expression
        # to the values list since we used a Literal expression
        values = update_query.values()
        values.append(suffix)
        
        # Execute the query
        result = conn.cursor().exec(update_query.query(), values)
        
        if not result or len(result) == 0:
            return json.dumps({})
        
        return json.dumps({
            'id': result[0]['id'],
            'title': result[0]['title'],
        })

def insert_user(conn, val):
    """
    Insert a new user and return the created record.
    Uses rick_db's insert query builder.
    """
    num = random.randrange(1_000_000)
    
    with conn.transaction():
        # Using rick_db's Insert builder
        insert_query = insert.Insert() \
            .into("users") \
            .values({
                "name": f'{val}{num}',
                "image": f'{val}image{num}'
            }) \
            .returning(["id", "name", "image"])
        
        # Execute the query
        result = conn.cursor().fetchone(insert_query.query(), insert_query.values())
        
        return json.dumps({
            'id': result['id'],
            'name': result['name'],
            'image': result['image'],
        })

def insert_movie(conn, val):
    """
    Insert a new movie with existing people as directors and actors.
    Uses rick_db's query builders for inserts and selects.
    """
    num = random.randrange(1_000_000)
    
    with conn.transaction():
        # Insert movie
        movie_insert = insert.Insert() \
            .into("movies") \
            .values({
                "title": f'{val["prefix"]}{num}',
                "image": f'{val["prefix"]}image{num}.jpeg',
                "description": f'{val["prefix"]}description{num}',
                "year": num % 100 + 1920  # A year between 1920 and 2019
            }) \
            .returning(["id", "title", "image", "description", "year"])
        
        movie = conn.cursor().fetchone(movie_insert.query(), movie_insert.values())
        
        # Get director and actors
        people_query = select.Select() \
            .fields(["id", "first_name", "last_name", "full_name(persons) as full_name", "image"]) \
            .from_("persons") \
            .where_in("id", val["people"][:4])
        
        people = conn.cursor().exec(people_query.query(), people_query.values())
        
        # Add director
        director_insert = insert.Insert() \
            .into("directors") \
            .values({
                "person_id": people[0]["id"], 
                "movie_id": movie["id"]
            })
        
        conn.cursor().exec(director_insert.query(), director_insert.values())
        
        # Add actors
        for i in range(1, 4):
            actor_insert = insert.Insert() \
                .into("actors") \
                .values({
                    "person_id": people[i]["id"], 
                    "movie_id": movie["id"]
                })
            
            conn.cursor().exec(actor_insert.query(), actor_insert.values())
            
    # Construct response object
    return json.dumps({
        'id': movie['id'],
        'image': movie['image'],
        'title': movie['title'],
        'year': movie['year'],
        'description': movie['description'],
        'directors': [
            {
                'id': people[0]['id'],
                'full_name': people[0]['full_name'],
                'image': people[0]['image'],
            }
        ],
        'cast': [
            {
                'id': people[i]['id'],
                'full_name': people[i]['full_name'],
                'image': people[i]['image'],
            } for i in range(1, 4)
        ],
    })

def insert_movie_plus(conn, val):
    """
    Insert a new movie with new people as directors and actors.
    Uses rick_db's query builders for the inserts.
    """
    num = random.randrange(1_000_000)
    
    with conn.transaction():
        # Insert movie
        movie_insert = insert.Insert() \
            .into("movies") \
            .values({
                "title": f'{val}{num}',
                "image": f'{val}image{num}.jpeg',
                "description": f'{val}description{num}',
                "year": num % 100 + 1920  # A year between 1920 and 2019
            }) \
            .returning(["id", "title", "image", "description", "year"])
        
        movie = conn.cursor().fetchone(movie_insert.query(), movie_insert.values())
        
        # Insert director
        director_insert = insert.Insert() \
            .into("persons") \
            .values({
                "first_name": f'{val}Alice',
                "last_name": f'{val}Director',
                "middle_name": '',
                "image": f'{val}image{num}.jpeg',
                "bio": ''
            }) \
            .returning(["id", "first_name", "last_name", "full_name(persons) as full_name", "image"])
        
        director = conn.cursor().fetchone(director_insert.query(), director_insert.values())
        
        # Insert actor 1
        actor1_insert = insert.Insert() \
            .into("persons") \
            .values({
                "first_name": f'{val}Billie',
                "last_name": f'{val}Actor',
                "middle_name": '',
                "image": f'{val}image{num+1}.jpeg',
                "bio": ''
            }) \
            .returning(["id", "first_name", "last_name", "full_name(persons) as full_name", "image"])
        
        actor1 = conn.cursor().fetchone(actor1_insert.query(), actor1_insert.values())
        
        # Insert actor 2
        actor2_insert = insert.Insert() \
            .into("persons") \
            .values({
                "first_name": f'{val}Cameron',
                "last_name": f'{val}Actor',
                "middle_name": '',
                "image": f'{val}image{num+2}.jpeg',
                "bio": ''
            }) \
            .returning(["id", "first_name", "last_name", "full_name(persons) as full_name", "image"])
        
        actor2 = conn.cursor().fetchone(actor2_insert.query(), actor2_insert.values())
        
        # Link director
        d_link_insert = insert.Insert() \
            .into("directors") \
            .values({
                "person_id": director["id"], 
                "movie_id": movie["id"]
            })
        
        conn.cursor().exec(d_link_insert.query(), d_link_insert.values())
        
        # Link actor 1
        a1_link_insert = insert.Insert() \
            .into("actors") \
            .values({
                "person_id": actor1["id"], 
                "movie_id": movie["id"]
            })
        
        conn.cursor().exec(a1_link_insert.query(), a1_link_insert.values())
        
        # Link actor 2
        a2_link_insert = insert.Insert() \
            .into("actors") \
            .values({
                "person_id": actor2["id"], 
                "movie_id": movie["id"]
            })
        
        conn.cursor().exec(a2_link_insert.query(), a2_link_insert.values())
    
    return json.dumps({
        'id': movie['id'],
        'image': movie['image'],
        'title': movie['title'],
        'year': movie['year'],
        'description': movie['description'],
        'directors': [
            {
                'id': director['id'],
                'full_name': director['full_name'],
                'image': director['image'],
            }
        ],
        'cast': [
            {
                'id': actor1['id'],
                'full_name': actor1['full_name'],
                'image': actor1['image'],
            },
            {
                'id': actor2['id'],
                'full_name': actor2['full_name'],
                'image': actor2['image'],
            }
        ],
    })

def setup(ctx, conn, queryname):
    """
    Set up the database for a benchmark.
    Uses rick_db's query builders for clean-up operations.
    """
    if queryname == 'update_movie':
        # Reset movie titles that were modified by the update_movie test
        update_query = update.Update() \
            .table("movies") \
            .set({"title": L("split_part(movies.title, '---', 1)")}) \
            .where_like("title", '%---%')
        
        conn.cursor().exec(update_query.query(), update_query.values())
        
    elif queryname == 'insert_user':
        # Delete test users
        delete_query = delete.Delete() \
            .from_("users") \
            .where_like("name", f'{INSERT_PREFIX}%')
        
        conn.cursor().exec(delete_query.query(), delete_query.values())
        
    elif queryname in {'insert_movie', 'insert_movie_plus'}:
        # Clean up test data - we need to use raw queries for some complex JOINs
        # in the DELETE statements that aren't directly supported by the query builder
        conn.cursor().exec("""
            DELETE FROM
                "directors" as D
            USING
                "movies" as M
            WHERE
                D.movie_id = M.id AND M.image LIKE %s
        """, [f'{INSERT_PREFIX}%'])
        
        conn.cursor().exec("""
            DELETE FROM
                "actors" as A
            USING
                "movies" as M
            WHERE
                A.movie_id = M.id AND M.image LIKE %s
        """, [f'{INSERT_PREFIX}%'])
        
        # Delete test movies
        delete_movies_query = delete.Delete() \
            .from_("movies") \
            .where_like("image", f'{INSERT_PREFIX}%')
        
        conn.cursor().exec(delete_movies_query.query(), delete_movies_query.values())
        
        # Delete test persons
        delete_persons_query = delete.Delete() \
            .from_("persons") \
            .where_like("image", f'{INSERT_PREFIX}%')
        
        conn.cursor().exec(delete_persons_query.query(), delete_persons_query.values())

def cleanup(ctx, conn, queryname):
    """
    Clean up after a benchmark.
    Reuses the setup function to perform cleanup.
    """
    if queryname in {'update_movie', 'insert_user', 'insert_movie', 'insert_movie_plus'}:
        # The clean up is the same as setup for mutation benchmarks
        setup(ctx, conn, queryname)