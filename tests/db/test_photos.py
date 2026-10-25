import pytest

from contract.embedders import Box, FaceDetection
from db.errors import Conflict, NotFound
from db.people import create_person, list_people
from db.photos import assign_face, list_photos, save_photo
from tests.helpers import vec


def face(x: int, y: int) -> FaceDetection:
    return FaceDetection(box=Box(x=x, y=y, width=50, height=50), embedding=vec(1.0, dims=128))


def test_save_photo_stores_faces_unlabelled(conn):
    out = save_photo(conn, "data/photos/a.jpg", 640, 480, [face(10, 20), face(300, 40)], "test")
    assert [(f.box.x, f.person_id) for f in out.faces] == [(10, None), (300, None)]


def test_photo_with_no_faces_is_stored(conn):
    out = save_photo(conn, "data/photos/b.jpg", 640, 480, [], "test")
    assert out.faces == [] and out.photo_id > 0


def test_box_outside_the_photo_is_rejected(conn):
    with pytest.raises(ValueError):
        save_photo(conn, "data/photos/c.jpg", 640, 480, [face(600, 20)], "test")   # 600 + 50 > 640


def test_reassigning_moves_the_label(conn):
    david = create_person(conn, "David", "grandson").id
    maria = create_person(conn, "Maria", "daughter").id
    face_id = save_photo(conn, "data/photos/d.jpg", 640, 480, [face(0, 0)], "test").faces[0].face_id
    assign_face(conn, face_id, david)
    assign_face(conn, face_id, maria)
    assert {p.name: p.face_count for p in list_people(conn)} == {"David": 0, "Maria": 1}


def test_unlabelling_a_face(conn):
    david = create_person(conn, "David", "grandson").id
    face_id = save_photo(conn, "data/photos/e.jpg", 640, 480, [face(0, 0)], "test").faces[0].face_id
    assign_face(conn, face_id, david)
    assign_face(conn, face_id, None)
    assert list_people(conn)[0].face_count == 0


def test_one_person_once_per_photo(conn):
    david = create_person(conn, "David", "grandson").id
    faces = save_photo(conn, "data/photos/f.jpg", 640, 480, [face(0, 0), face(100, 0)], "test").faces
    assign_face(conn, faces[0].face_id, david)
    with pytest.raises(Conflict):
        assign_face(conn, faces[1].face_id, david)


def test_assign_reports_what_is_missing(conn):
    david = create_person(conn, "David", "grandson").id
    with pytest.raises(NotFound, match="face"):
        assign_face(conn, 999, david)
    face_id = save_photo(conn, "data/photos/g.jpg", 640, 480, [face(0, 0)], "test").faces[0].face_id
    with pytest.raises(NotFound, match="person"):
        assign_face(conn, face_id, 999)


def test_list_photos_shows_current_labels(conn):
    david = create_person(conn, "David", "grandson").id
    face_id = save_photo(conn, "data/photos/h.jpg", 640, 480, [face(5, 5)], "test").faces[0].face_id
    save_photo(conn, "data/photos/i.jpg", 640, 480, [], "test")
    assign_face(conn, face_id, david)
    photos = list_photos(conn)
    assert [len(p.faces) for p in photos] == [1, 0]
    assert photos[0].faces[0].person_id == david
