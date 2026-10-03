"""Build the current Windows GUI with verified dependency materials; no ADB calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.3.2'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--materials', type=Path, required=True)
    args = parser.parse_args()
    materials = args.materials.resolve()
    expected = json.loads((ROOT/'materials-sha256.json').read_text(encoding='utf-8'))
    for name, digest in expected.items():
        path = materials/name
        if not path.is_file() or sha(path) != digest:
            raise SystemExit('Dependency material mismatch: '+name)
    out = ROOT/'dist'/('SO51D-Root-Tool-'+VERSION)
    if out.exists():
        raise SystemExit('Output exists; use a fresh build directory: '+str(out))
    out.mkdir(parents=True)
    for name in expected:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(materials/name, target)
    for directory in ['gui','scripts','profiles','artifacts','licenses','tests','docs','evidence']:
        shutil.copytree(ROOT/directory,out/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['checksums.json','tools-manifest.json','使用说明.txt','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','README.md','PRIVACY.md','SECURITY.md']:
        shutil.copy2(ROOT/name,out/name)
    (out/'sources').mkdir()
    for source_archive in (ROOT/'third_party').glob('*.zip'):
        shutil.copy2(source_archive, out/'sources'/source_archive.name)
    provenance = {'runtime':'CPython 3.14.0b1 Windows x64','gui_build_python':sys.version.split()[0],
                  'gui_pyinstaller':'6.22.0','version':VERSION}
    (out/'runtime-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    manifest=json.loads((out/'tools-manifest.json').read_text(encoding='utf-8'))
    archive=out/'downloads'/manifest['packages'][0]['name']
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(out/'downloads/ghostlock-arm64','ghostlock-arm64')
        z.writestr('build.json',json.dumps({'source_commit':manifest['source_commit'],
          'diagnostic_build':manifest['diagnostic_build'], 'native_sha256':sha(out/'downloads/ghostlock-arm64'),
          'toolchain':'ONDK r30.1','source':'native/src in this version'},indent=2))
    manifest['packages'][0]['sha256']=sha(archive)
    manifest['packages'][0]['url']='https://github.com/2060823826lzc-beep/so51d-root-guide/releases/download/v'+VERSION+'/'+archive.name
    (out/'tools-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
             '--name','SO51D-Root-Tool','--icon',str(ROOT/'gui/app.ico'),
             '--distpath',str(out),'--workpath',str(ROOT/'build/gui'),
             '--specpath',str(ROOT/'build'),str(ROOT/'gui/app.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    (out/'logs').mkdir(exist_ok=True)
    (out/'history').mkdir(exist_ok=True)
    (out/'attempts').mkdir(exist_ok=True)
    # Ship the GUI dependency licenses, including the bootloader exception.
    import PyInstaller
    import importlib.metadata
    package=Path(importlib.metadata.distribution('pyinstaller').locate_file('pyinstaller-6.22.0.dist-info/licenses'))
    for name in ['COPYING.txt']:
        source=package/name
        if source.exists(): shutil.copy2(source,out/'licenses'/('PyInstaller-'+name))
    base=Path(sys.base_prefix)
    if (base/'LICENSE.txt').is_file():
        shutil.copy2(base/'LICENSE.txt',out/'licenses/CPython-3.12-LICENSE.txt')
    for name in ['tcl8.6','tk8.6']:
        source=base/'tcl'/name/'license.terms'
        if source.exists(): shutil.copy2(source,out/'licenses'/(name+'-license.terms'))
    subprocess.run([str(out/'SO51D-Root-Tool.exe'),'--self-test'],check=True,timeout=60)
    test=json.loads((out/'logs/exe-ui-self-test.json').read_text(encoding='utf-8'))
    (ROOT/'build/gui-self-test.json').write_text(json.dumps(test,ensure_ascii=False,indent=2),encoding='utf-8')
    for name in ['logs','gui.lock']:
        path=(out/name).resolve()
        assert path.is_relative_to((ROOT/'dist').resolve())
        if path.is_dir(): shutil.rmtree(path)
        elif path.exists(): path.unlink()
    entries={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'bundle-sha256.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    target=Path(shutil.make_archive(str(out),'zip',out.parent,out.name))
    (target.parent/'SHA256SUMS.txt').write_text(sha(target)+'  '+target.name+'\n'+sha(archive)+'  '+archive.name+'\n',encoding='utf-8')
    for source_archive in (ROOT/'third_party').glob('*.zip'):
        shutil.copy2(source_archive, target.parent/source_archive.name)
    print(target)

if __name__ == '__main__':
    main()
