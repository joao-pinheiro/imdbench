from rick_db import fieldmapper


@fieldmapper(tablename='movies', pk='id')
class MovieRecord:
    id = 'id'
    image = 'image'
    title = 'title'
    year = 'year'
    description = 'description'
    avg_rating = 'avg_rating' # computed field

@fieldmapper(tablename='users', pk='id')
class UserRecord:
    id = 'id'
    name = 'name'
    image = 'image'


@fieldmapper(tablename='persons', pk='id')
class PersonRecord:
    id = 'id'
    first_name = 'first_name'
    middle_name = 'middle_name'
    last_name = 'last_name'
    image = 'image'
    bio = 'bio'


@fieldmapper(tablename='directors', pk='id')
class DirectorRecord:
    id = 'id'
    list_order = 'list_order'
    person_id = 'person_id'
    movie_id = 'movie_id'
    full_name = 'full_name' # computed record

@fieldmapper(tablename='actors', pk='id')
class ActorRecord:
    id = 'id'
    list_order = 'list_order'
    person_id = 'person_id'
    movie_id = 'movie_id'


@fieldmapper(tablename='reviews', pk='id')
class ReviewRecord:
    id = 'id'
    body = 'body'
    rating = 'rating'
    creation_time = 'creation_time'
    author_id = 'author_id'
    movie_id = 'movie_id'

@fieldmapper()
class GetUserRecord:
    id = 'id',
    name = 'name',
    image = 'image',
    review_id = 'review_id',
    review_body = 'review_body',
    review_rating = 'review_rating',
    movie_id = 'movie_id',
    movie_image = 'movie_image',
    movie_title = 'movie_title',
    movie_avg_rating = 'movie_avg_rating'
