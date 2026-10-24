"""Face recognition foundation built on face_recognition 1.3 (dlib).

Quick start:

    from facerec import FaceConfig, FaceRecognizer, load_image
    from facerec.enroll import load_or_build_database

    recognizer = FaceRecognizer(config=FaceConfig(tolerance=0.55))
    load_or_build_database(recognizer)  # data/known_faces -> data/face_db.npz
    for face in recognizer.identify(load_image("group.jpg")):
        print(face.name, face.confidence, face.location)

Importing this package is cheap; dlib and the face models load when the first
FaceRecognizer is created.
"""

from .config import FaceConfig
from .database import UNKNOWN, FaceDatabase, Match
from .imaging import load_image
from .recognizer import FaceRecognizer, RecognizedFace

__all__ = ["UNKNOWN", "FaceConfig", "FaceDatabase", "FaceRecognizer", "Match", "RecognizedFace", "load_image"]
