"""Export genuine native frames to PNG/GIF and optional MP4; no generative edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--frames",type=Path,default=ROOT/"results/animation/raw/clip04")
    cli.add_argument("--interval-ms",type=int,default=180)
    args=cli.parse_args()
    files=sorted(args.frames.glob("frame-*.png"))
    if len(files)<2:
        raise ValueError("Record at least two native frames")
    hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if len(hashes)<2:
        raise ValueError("Captured frames are identical; motion is not verified")
    crop=(72,0,1830,910)
    frames=[]
    for p in files:
        with Image.open(p) as source:
            cropped=source.crop(crop)
            resized=cropped.resize((1120,round(cropped.height*1120/cropped.width)),Image.Resampling.LANCZOS)
            frames.append(resized.quantize(128,dither=Image.Dither.NONE))
    with Image.open(files[len(files)//3]) as source:
        source.crop(crop).save(ROOT/"model/store-view.png")
    target=ROOT/"model/store-animation.gif"
    frames[0].save(target,save_all=True,append_images=frames[1:],duration=args.interval_ms,
                   loop=0,optimize=True,disposal=2)
    ffmpeg=shutil.which("ffmpeg")
    fallback=Path.home()/"Documents/marketing-agency/video-studio/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe"
    if not ffmpeg and fallback.exists():
        ffmpeg=str(fallback)
    mp4=False
    mp4_error=None
    if ffmpeg:
        try:
            subprocess.run([ffmpeg,"-y","-loglevel","error","-framerate",str(1000/args.interval_ms),
                            "-i",str(args.frames/"frame-%04d.png"),"-vf",
                            "crop=1758:910:72:0,scale=1600:-2:flags=lanczos,format=yuv420p",
                            "-c:v","libx264","-crf","20",str(ROOT/"model/store-animation.mp4")],check=True)
            mp4=True
        except (OSError,subprocess.CalledProcessError) as error:
            mp4_error=str(error)
            (ROOT/"model/store-animation.mp4").unlink(missing_ok=True)
            print("Optional MP4 encoding failed; the PNG and GIF were produced:",error)
    info={"source":"Native AnyLogic Animation experiment, P2StoreAnimation04",
          "frames":len(files),"distinct_frames":len(hashes),"interval_ms":args.interval_ms,
          "duration_seconds":len(files)*args.interval_ms/1000,"crop":crop,
          "processing":"Only crop/rescale/palette/video encoding; no generated content",
          "customer_and_truck_paths":"Illustrative read-only animation; no queueing KPIs",
          "mp4_produced":mp4,"mp4_error":mp4_error,"gif_sha256":hashlib.sha256(target.read_bytes()).hexdigest()}
    (ROOT/"model/capture-manifest.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    print(json.dumps(info,indent=2))


if __name__=="__main__":
    main()
