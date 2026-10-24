# Known faces

Put photos of people to recognize here. Everything in this folder except this
README is git-ignored, so photos of real people never get committed.

```
data/known_faces/
├── alice/            one folder per person (folder name = the name shown)
│   ├── front.jpg
│   └── glasses.png
└── bob.jpg           or a single photo named after the person
```

Tips:
- 3–5 photos per person (different angles/lighting) beat one perfect photo.
- One person per photo. If several faces of similar size are found, the photo is
  skipped instead of guessing; a clearly dominant face (e.g. a selfie) is used.
- Formats: JPG, PNG, WebP, AVIF, BMP, GIF, TIFF. iPhone HEIC photos are
  skipped with a warning: export them as JPG (or set Camera > Formats >
  Most Compatible).
- Or let the webcam take the photos: `python -m facerec capture "Alice"`.

The database (`data/face_db.npz`) rebuilds automatically when photos are added,
removed or changed here. Force a rebuild with `python -m facerec enroll`.
