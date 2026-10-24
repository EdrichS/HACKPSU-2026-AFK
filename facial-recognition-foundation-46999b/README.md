# HACKPSU: face recognition foundation

Face detection and recognition built on
[face_recognition 1.3](https://github.com/ageitgey/face_recognition) (dlib's
ResNet face encoder). The `facerec` package wraps it with enrollment from a
photo folder, a saved encodings database, live webcam recognition, and a CLI.
Voice recognition will sit next to it later.

## Setup

face_recognition depends on **dlib**, which pip compiles from source (about 1–2
minutes; pip fetches CMake on its own). You need a C++ compiler and the Python
headers:

| OS | Install first |
|---|---|
| Ubuntu/Debian | `sudo apt install build-essential python3-dev python3-venv` |
| macOS | `xcode-select --install` |
| Windows | Visual Studio Build Tools with "Desktop development with C++" |

Optional (Linux): `sudo apt install libopenblas-dev liblapack-dev` before
installing makes dlib faster.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt
```

On Windows (PowerShell) create and activate the venv with `py -m venv .venv`
and `.venv\Scripts\Activate.ps1` instead.

If `python3 -m venv` fails with "ensurepip is not available", install your
Python's venv package (`sudo apt install python3.14-venv`, matching your
version).

Check it works:

```bash
pytest
```

### Known install problems

- **`Please install face_recognition_models ...` and the program exits**, even
  though it's installed. face_recognition_models imports `pkg_resources`, which
  setuptools 82+ removed (and new venvs don't include setuptools at all), and
  face_recognition hides the real error. `requirements.txt` pins
  `setuptools<81`; if it happens anyway run `pip install "setuptools<81"`.
  (`facerec` detects this and prints the fix.)
- **`compute_face_descriptor(): incompatible function arguments`**: the image
  array isn't C-contiguous, usually from `frame[:, :, ::-1]`. Use
  `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`; `facerec` handles this for you.
- `face_recognition.__version__` reports `1.2.3` on 1.3.0; that's a typo in the
  release, check with `pip show face_recognition`.

## Usage

1. Add photos: `data/known_faces/<name>/*.jpg` (see
   [data/known_faces/README.md](data/known_faces/README.md)), or capture from the
   webcam:

   ```bash
   python -m facerec capture "Alice"
   ```

2. Recognize:

   ```bash
   python -m facerec live
   ```

   ```bash
   python -m facerec identify group_photo.jpg --out data/annotated/
   ```

| Command | What it does |
|---|---|
| `enroll` | Rebuild `data/face_db.npz` from `data/known_faces/` (also happens automatically when photos change) |
| `capture NAME` | Take `--samples` photos of one person from the webcam and enroll them |
| `identify IMG...` | Print who is in each image; `--out DIR` saves annotated copies. Detects at full resolution (a few seconds for a 12MP photo); `--max-size 1600` is faster but misses small faces in crowd shots |
| `live` | Webcam window with names and boxes. `q`/Esc quits. `--source video.mp4` works too; `--no-display` logs names instead (needed over SSH or without a desktop) |
| `list` | Who is enrolled and how many encodings each |

Useful options (all commands): `--tolerance 0.5` (stricter), `--upsample 2`
(find smaller faces), `--model cnn` (more accurate detection; without a CUDA
build of dlib it takes seconds and several GB of RAM per photo, so pair it
with `--upsample 0`). Video: `--scale 1` (find smaller/farther faces) or
`--scale 0.25` (faster), `--every 1` (recognize every frame).
`python -m facerec <command> --help` for everything.

## Using it from Python

```python
from facerec import FaceConfig, FaceRecognizer, load_image
from facerec.enroll import load_or_build_database
from facerec.video import run_live

recognizer = FaceRecognizer(config=FaceConfig(tolerance=0.55))
load_or_build_database(recognizer)  # defaults: data/known_faces -> data/face_db.npz

# Still images (RGB)
for face in recognizer.identify(load_image("photo.jpg")):
    print(face.name, f"{face.confidence:.0%}", face.location)  # location = (top, right, bottom, left)

# Live video: on_faces is where app logic goes
def on_faces(faces, frame):  # every recognition pass; frame is the raw BGR image
    for face in faces:
        if face.is_known:
            print("saw", face.name)

run_live(recognizer, source=0, on_faces=on_faces)
```

## How it works

1. **Detect**: HOG (default, CPU) or CNN detector returns face boxes. Live
   video detects on a half-size frame for speed; photos are searched at full
   resolution (with `--model cnn`, on a copy at most 1600px wide to bound
   memory).
2. **Encode**: each face is aligned with facial landmarks and turned into a
   128-number vector by dlib's ResNet. `identify` and `live` encode from the
   full-resolution image, so downscaling for detection doesn't hurt accuracy;
   enrollment photos are shrunk to 1600px first, which is still far more
   detail than the 150x150 face crop the encoder uses.
3. **Match**: the closest enrolled vector wins if its distance is at most
   `tolerance` (default 0.6, the value dlib's model was tuned for; lower is
   stricter). Otherwise the face is `Unknown`. `confidence` is a 0–1 display
   score where `tolerance` maps to 50%.

## Layout

```
facerec/
  config.py      FaceConfig: tolerance, models, video speed settings
  recognizer.py  FaceRecognizer: detect / encode / identify
  database.py    FaceDatabase: names + encodings, nearest match, .npz save/load
  enroll.py      build the database from data/known_faces/ (rebuilt when photos change)
  video.py       live recognition loop, webcam enrollment
  imaging.py     image loading (EXIF-aware), color conversion, drawing
  cli.py         python -m facerec ...
tests/           unit tests + integration tests on a public-domain NASA photo
data/            enrollment photos, database, annotated output (all git-ignored)
```

Face photos and the encodings database are biometric data of real people: they
are git-ignored, stay local, and should only include people who agreed to it.
