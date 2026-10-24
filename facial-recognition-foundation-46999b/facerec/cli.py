"""Command line interface: python -m facerec <command> --help"""

import argparse
import logging
import sys
from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_FACES_DIR, DETECTION_MODELS, ENCODING_MODELS, PROJECT_ROOT, FaceConfig
from .enroll import ENROLL_JITTERS

logger = logging.getLogger("facerec")


def _common_options():
    parser = argparse.ArgumentParser(add_help=False)
    defaults = FaceConfig()
    group = parser.add_argument_group("common options")
    group.add_argument("--faces-dir", type=Path, default=DEFAULT_FACES_DIR, help=f"folder of labelled photos (default: {DEFAULT_FACES_DIR.relative_to(PROJECT_ROOT)})")
    group.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help=f"encodings cache file (default: {DEFAULT_DB_PATH.relative_to(PROJECT_ROOT)})")
    group.add_argument("--tolerance", type=float, default=defaults.tolerance, help="max match distance; lower is stricter (default: %(default)s)")
    group.add_argument("--model", choices=DETECTION_MODELS, default=defaults.detection_model, help="face detector (default: %(default)s)")
    group.add_argument("--upsample", type=int, default=defaults.upsample, help="upsample passes to find small faces (default: %(default)s)")
    group.add_argument("--encoding-model", choices=ENCODING_MODELS, default=defaults.encoding_model, help="landmark model used for alignment (default: %(default)s)")
    group.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def _video_options():
    parser = argparse.ArgumentParser(add_help=False)
    defaults = FaceConfig()
    group = parser.add_argument_group("video options")
    group.add_argument("--source", default="0", help="camera index, video file or stream URL (default: %(default)s)")
    group.add_argument("--no-display", action="store_true", help="don't open a window; log results instead")
    group.add_argument("--scale", type=float, default=defaults.frame_scale, help="detect on frames shrunk by this factor (default: %(default)s)")
    group.add_argument("--every", type=int, default=defaults.process_every_n_frames, help="run recognition every N frames (default: %(default)s)")
    return parser


def build_parser():
    common, video = _common_options(), _video_options()
    parser = argparse.ArgumentParser(prog="python -m facerec", description="Face recognition built on face_recognition 1.3 + dlib.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("enroll", parents=[common], help="(re)build the database from --faces-dir photos")
    p.add_argument("--jitters", type=int, default=ENROLL_JITTERS, help="re-samples per photo (default: %(default)s)")

    p = sub.add_parser("capture", parents=[common, video], help="enroll a person from the webcam")
    p.add_argument("name", help="person's name (also their folder name)")
    p.add_argument("--samples", type=int, default=5, help="photos to take (default: %(default)s)")
    p.add_argument("--jitters", type=int, default=ENROLL_JITTERS, help="re-samples per photo (default: %(default)s)")

    p = sub.add_parser("identify", parents=[common], help="recognize faces in image files")
    p.add_argument("images", nargs="+", type=Path, help="image files")
    p.add_argument("--out", type=Path, help="write annotated copies into this folder")
    p.add_argument(
        "--max-size",
        type=int,
        default=FaceConfig.max_image_size,
        help="detect on a copy at most this many px wide, 0 = full resolution (default: full resolution for hog, 1600 for cnn)",
    )

    sub.add_parser("live", parents=[common, video], help="recognize faces from a webcam or video")

    sub.add_parser("list", parents=[common], help="show who is enrolled")
    return parser


def _make_config(args):
    return FaceConfig(
        tolerance=args.tolerance,
        detection_model=args.model,
        upsample=args.upsample,
        encoding_model=args.encoding_model,
        frame_scale=getattr(args, "scale", FaceConfig.frame_scale),
        process_every_n_frames=getattr(args, "every", FaceConfig.process_every_n_frames),
        max_image_size=getattr(args, "max_size", FaceConfig.max_image_size),
    )


def _make_recognizer(args, build_if_stale=True):
    # Imported here so `--help` and argument errors don't wait for dlib + model loading.
    from .database import FaceDatabase
    from .enroll import load_or_build_database
    from .recognizer import FaceRecognizer

    recognizer = FaceRecognizer(config=_make_config(args))
    if build_if_stale:
        load_or_build_database(recognizer, args.faces_dir, args.db)
    elif args.db.exists():
        recognizer.database = FaceDatabase.load(args.db)
    return recognizer


def cmd_enroll(args):
    from .enroll import build_database
    from .recognizer import FaceRecognizer

    recognizer = FaceRecognizer(config=_make_config(args))
    if not args.faces_dir.is_dir():
        logger.error("faces folder %s does not exist; add photos as %s/<name>/photo.jpg", args.faces_dir, args.faces_dir)
        return 1
    database, report = build_database(recognizer, args.faces_dir, num_jitters=args.jitters)
    database.save(args.db)
    logger.info("%s -> %s", report.summary(), args.db)
    return 0


def cmd_capture(args):
    from .video import capture_enrollment

    recognizer = _make_recognizer(args)
    saved = capture_enrollment(
        recognizer,
        args.name,
        args.faces_dir,
        source=args.source,
        samples=args.samples,
        display=not args.no_display,
        num_jitters=args.jitters,
    )
    if not saved:
        logger.error("no samples captured for %s", args.name)
        return 1
    recognizer.database.save(args.db)
    logger.info("added %d sample(s) of %s -> %s", len(saved), args.name, args.db)
    return 0


def cmd_identify(args):
    from .imaging import draw_faces, load_image, rgb_to_bgr, save_bgr

    recognizer = _make_recognizer(args)
    if len(recognizer.database) == 0:
        logger.warning("database is empty: every face will be %r. Add photos to %s first.", "Unknown", args.faces_dir)
    status = 0
    used_out_paths = set()
    for path in args.images:
        try:
            rgb = load_image(path)
        except (OSError, ValueError) as exc:
            logger.error("%s: cannot read image (%s)", path, exc)
            status = 1
            continue
        faces = recognizer.identify(rgb)
        print(f"{path}: {len(faces)} face(s)")
        for face in faces:
            print(f"  {face.name:<20} distance={face.distance:.3f} confidence={face.confidence:.0%} box(t,r,b,l)={face.location}")
        if args.out:
            out_path = args.out / f"{path.stem}_annotated.jpg"
            n = 2
            while out_path in used_out_paths:  # same file name from different folders
                out_path = args.out / f"{path.stem}_annotated_{n}.jpg"
                n += 1
            used_out_paths.add(out_path)
            save_bgr(out_path, draw_faces(rgb_to_bgr(rgb), faces))
            print(f"  -> {out_path}")
    return status


def cmd_live(args):
    from .video import run_live

    recognizer = _make_recognizer(args)
    logger.info("known people: %s", ", ".join(recognizer.database.people) or "(none)")
    if run_live(recognizer, source=args.source, display=not args.no_display) == 0:
        logger.error("no frames received from video source %s", args.source)
        return 1
    return 0


def cmd_list(args):
    from .database import FaceDatabase

    if not args.db.exists():
        print(f"no database at {args.db}; run `python -m facerec enroll` first")
        return 0
    counts = FaceDatabase.load(args.db).counts()
    if not counts:
        print("database is empty")
    for name, count in counts.items():
        print(f"{name}: {count} encoding(s)")
    return 0


COMMANDS = {"enroll": cmd_enroll, "capture": cmd_capture, "identify": cmd_identify, "live": cmd_live, "list": cmd_list}


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        _make_config(args)  # validate numeric options before loading models
        return COMMANDS[args.command](args)
    except KeyboardInterrupt:
        return 130
    except MemoryError:
        logger.error("error: out of memory. The cnn detector needs several GB per image on a CPU; use --model hog or --upsample 0.")
        return 1
    except (ImportError, RuntimeError, ValueError, OSError) as exc:
        logger.error("error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
