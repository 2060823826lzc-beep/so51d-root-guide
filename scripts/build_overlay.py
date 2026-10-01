"""Build the small DEX JAR with a local JDK and Android SDK (no downloads)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from common import ROOT, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android-jar', required=True, type=Path, help='Android API 35 的 android.jar')
    parser.add_argument('--r8-jar', required=True, type=Path, help='Android Build Tools 的 lib/d8.jar 或 r8.jar')
    parser.add_argument('--java-home', type=Path, default=os.environ.get('JAVA_HOME'), help='JDK 17 根目录；也可用 JAVA_HOME/PATH')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/gesture-pill-overlay.jar')
    args = parser.parse_args()
    for path in [args.android_jar, args.r8_jar]:
        if not path.is_file():
            parser.error(f'文件不存在：{path}')
    suffix = '.exe' if os.name == 'nt' else ''
    def tool(name):
        found = str(args.java_home / 'bin' / (name + suffix)) if args.java_home else shutil.which(name)
        if not found or not Path(found).is_file():
            parser.error(f'找不到 {name}，需要完整 JDK。')
        return found
    build = ROOT / 'build'
    classes = build / 'classes'
    dex = build / 'dex'
    classes.mkdir(parents=True, exist_ok=True)
    dex.mkdir(parents=True, exist_ok=True)
    def run(*command):
        subprocess.run([str(x) for x in command], check=True, timeout=120)
    run(tool('javac'), '--release', '8', '-cp', args.android_jar, '-d', classes, ROOT / 'src/GesturePillOverlay.java')
    run(tool('jar'), 'cf', build / 'classes.jar', '-C', classes, '.')
    run(tool('java'), '-cp', args.r8_jar, 'com.android.tools.r8.D8', '--min-api', '26',
        '--lib', args.android_jar, '--output', dex, build / 'classes.jar')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Fixed ZIP metadata; DEX still depends on JDK/R8 versions.
    with zipfile.ZipFile(args.output, 'w') as archive:
        entry = zipfile.ZipInfo('classes.dex', date_time=(2026, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, (dex / 'classes.dex').read_bytes())
    print(f'{sha256(args.output)}  {args.output}')


if __name__ == '__main__':
    main()
