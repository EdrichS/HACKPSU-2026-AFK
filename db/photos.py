"""Photos and the faces found in them; a face's label is its person_id (NULL = unlabelled)."""

import psycopg
from psycopg import errors

from contract.embedders import Box, FaceDetection
from contract.setup_api import DetectedFace, PhotoOut
from db.errors import Conflict, NotFound


def save_photo(
    conn: psycopg.Connection,
    file_path: str,
    width: int,
    height: int,
    faces: list[FaceDetection],
    model: str,
) -> PhotoOut:
    """Store a photo and its faces, all unlabelled. Raise ValueError if a box doesn't fit."""
    for f in faces:
        b = f.box
        if b.x < 0 or b.y < 0 or b.x + b.width > width or b.y + b.height > height:
            raise ValueError(f"face box {b} doesn't fit inside a {width}x{height} photo")
    photo_id = conn.execute(
        "INSERT INTO photos (file_path, width, height) VALUES (%(path)s, %(width)s, %(height)s) RETURNING id",
        {"path": file_path, "width": width, "height": height},
    ).fetchone()[0]
    detected = []
    for f in faces:
        face_id = conn.execute(
            """
            INSERT INTO face_samples (photo_id, box_x, box_y, box_width, box_height, model, embedding)
            VALUES (%(photo_id)s, %(x)s, %(y)s, %(w)s, %(h)s, %(model)s, %(embedding)s::vector)
            RETURNING id
            """,
            {
                "photo_id": photo_id,
                "x": f.box.x,
                "y": f.box.y,
                "w": f.box.width,
                "h": f.box.height,
                "model": model,
                "embedding": f.embedding,
            },
        ).fetchone()[0]
        detected.append(DetectedFace(face_id=face_id, box=f.box, person_id=None))
    return PhotoOut(photo_id=photo_id, width=width, height=height, faces=detected)


def assign_face(conn: psycopg.Connection, face_id: int, person_id: int | None) -> None:
    """Label a face with a person, or unlabel it with None. Reassigning moves the label."""
    try:
        cur = conn.execute(
            "UPDATE face_samples SET person_id = %(person_id)s WHERE id = %(face_id)s",
            {"person_id": person_id, "face_id": face_id},
        )
    except (errors.ForeignKeyViolation, errors.NumericValueOutOfRange):
        raise NotFound("person") from None
    except errors.UniqueViolation:
        raise Conflict(
            "That person is already labelled on another face in this photo. Reassign that face first."
        ) from None
    if cur.rowcount == 0:
        raise NotFound("face")


def list_photos(conn: psycopg.Connection) -> list[PhotoOut]:
    """Every photo with its faces' current labels, from one statement (one snapshot)."""
    photos: dict[int, PhotoOut] = {}
    rows = conn.execute(
        """
        SELECT ph.id AS photo_id, ph.width, ph.height,
               f.id AS face_id, f.box_x, f.box_y, f.box_width, f.box_height, f.person_id
        FROM photos ph
        LEFT JOIN face_samples f ON f.photo_id = ph.id
        ORDER BY ph.id, f.id
        """
    )
    for photo_id, width, height, face_id, x, y, w, h, person_id in rows:
        photo = photos.setdefault(photo_id, PhotoOut(photo_id=photo_id, width=width, height=height, faces=[]))
        if face_id is not None:  # a photo with no faces gives one row of NULL face columns
            box = Box(x=x, y=y, width=w, height=h)
            photo.faces.append(DetectedFace(face_id=face_id, box=box, person_id=person_id))
    return list(photos.values())


def photo_file(conn: psycopg.Connection, photo_id: int) -> str | None:
    row = conn.execute("SELECT file_path FROM photos WHERE id = %(id)s", {"id": photo_id}).fetchone()
    return row[0] if row else None
