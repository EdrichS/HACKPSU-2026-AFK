import pytest

from db.match import Candidate, decide, nearest_people
from tests.helpers import insert_face, insert_person, insert_photo, insert_voice, vec


def test_unlabelled_faces_count_as_not_enrolled(conn):                 # Review Focus 2
    david = insert_person(conn, "David", "grandson")
    q = vec(1.0, dims=128)
    insert_face(conn, insert_photo(conn), person_id=None, embedding=q)     # never labelled, distance 0
    insert_face(conn, insert_photo(conn), person_id=david, embedding=vec(0.9, dims=128))
    got = nearest_people(conn, "face", "l2", q)
    assert [c.person_id for c in got] == [None, david]
    assert decide(got, cutoff=0.6, margin=0.05) == "not_sure"


def test_each_person_is_scored_by_their_best_sample(conn):
    david = insert_person(conn, "David", "grandson")
    maria = insert_person(conn, "Maria", "daughter")
    insert_face(conn, insert_photo(conn), person_id=david, embedding=vec(0.8, dims=128))
    insert_face(conn, insert_photo(conn), person_id=david, embedding=vec(0.9, dims=128))
    insert_face(conn, insert_photo(conn), person_id=maria, embedding=vec(0.7, dims=128))
    got = nearest_people(conn, "face", "l2", vec(1.0, dims=128))
    assert [c.name for c in got] == ["David", "Maria"]       # ranking samples, not people, gives David twice
    assert [c.distance for c in got] == pytest.approx([0.1, 0.3], abs=1e-6)


def test_no_samples_means_no_candidates(conn):
    insert_person(conn, "David", "grandson")
    assert nearest_people(conn, "voice", "cosine", vec(1.0, dims=192)) == []


def test_cosine_ignores_vector_length(conn):
    david = insert_person(conn, "David", "grandson")
    insert_voice(conn, david, embedding=vec(2.0, dims=192))
    q = vec(1.0, dims=192)
    assert nearest_people(conn, "voice", "cosine", q)[0].distance == pytest.approx(0.0, abs=1e-6)
    assert nearest_people(conn, "voice", "l2", q)[0].distance == pytest.approx(1.0, abs=1e-6)


def test_an_empty_or_broken_query_matches_nobody(conn):
    insert_voice(conn, insert_person(conn, "David", "grandson"))
    assert nearest_people(conn, "voice", "cosine", vec(dims=192)) == []
    assert nearest_people(conn, "voice", "cosine", vec(float("nan"), dims=192)) == []


def test_a_match_carries_the_card(conn):
    david = insert_person(conn, "David", "grandson")
    conn.execute("UPDATE people SET small_context = 'He is a nurse.' WHERE id = %s", (david,))
    insert_voice(conn, david)
    assert nearest_people(conn, "voice", "cosine", vec(1.0, dims=192))[0].small_context == "He is a nurse."


@pytest.mark.parametrize("candidates, expected", [
    ([], "no_match"),                                   # nobody enrolled
    ([(1, 0.62)], "no_match"),                          # the nearest person isn't under the cutoff
    ([(1, 0.60)], "no_match"),                          # exactly at the cutoff isn't under it
    ([(1, 0.40)], 0),                                   # one person, under the cutoff
    ([(1, 0.40), (2, 0.42)], "not_sure"),               # look-alike relatives within the margin   (Review Focus 4)
    ([(1, 0.40), (2, 0.50)], 0),                        # a clear winner
    ([(None, 0.30), (1, 0.50)], "not_sure"),            # the nearest face was never labelled
    ([(1, 0.40), (None, 0.42)], "not_sure"),            # an unlabelled face is within the margin
    ([(1, float("nan"))], "no_match"),                  # <=> against a zero vector gives NaN
    ([(1, float("nan")), (2, float("nan"))], "no_match"),
])
def test_decide(candidates, expected):
    cands = [Candidate(pid, None if pid is None else f"p{pid}", None if pid is None else "family",
                       None if pid is None else "", d) for pid, d in candidates]
    want = cands[expected] if isinstance(expected, int) else expected
    assert decide(cands, cutoff=0.6, margin=0.05) == want
