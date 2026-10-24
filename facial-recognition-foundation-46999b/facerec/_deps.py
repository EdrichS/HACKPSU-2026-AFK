"""Import face_recognition with clear errors for the common install failures.

face_recognition 1.3 does `import face_recognition_models` inside a bare
try/except and calls quit() if it fails, printing a misleading "please install
face_recognition_models" message. The usual real cause is that
face_recognition_models imports `pkg_resources`, which is missing when
setuptools isn't installed (new venvs don't include it) or is 82+ (it was
removed). Importing face_recognition_models ourselves first surfaces the
real error.
"""

import warnings

_face_recognition = None


def load_face_recognition():
    """Return the face_recognition module, importing it (and its models) on first use."""
    global _face_recognition
    if _face_recognition is not None:
        return _face_recognition

    with warnings.catch_warnings():
        # face_recognition_models triggers setuptools' pkg_resources deprecation warning.
        warnings.filterwarnings("ignore", message=r".*pkg_resources is deprecated.*")
        try:
            import face_recognition_models  # noqa: F401
        except ModuleNotFoundError as exc:
            if exc.name == "pkg_resources":
                raise ImportError(
                    "face_recognition_models needs pkg_resources, which is missing: setuptools is "
                    'not installed or is 82+ (which removed it). Fix with:  pip install "setuptools<81"'
                ) from exc
            if exc.name == "face_recognition_models":
                raise ImportError(
                    "face_recognition_models is not installed. Fix with:  "
                    "pip install face_recognition_models==0.3.0"
                ) from exc
            raise
        try:
            import face_recognition
        except ModuleNotFoundError as exc:
            if exc.name == "dlib":
                raise ImportError(
                    "dlib is not installed. It builds from source and needs CMake and a C++ "
                    "compiler; see README.md for platform-specific steps."
                ) from exc
            raise

    _face_recognition = face_recognition
    return face_recognition
