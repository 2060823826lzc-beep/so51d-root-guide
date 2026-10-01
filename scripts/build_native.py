"""Run the repository's native compiler/linker arguments on Windows without Make."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
import time
import argparse

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--toolchain', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source = HERE.parent / 'native'
label = 'so51d-observe-20260929-01'
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
compiler = args.toolchain.resolve() / 'clang++.exe'
makefile = (source/'src/Makefile').read_text()
section = makefile.split('CXX_SRCS :=',1)[1].split('\n\n',1)[0]
files = re.findall(r'core/[\w/]+\.cpp',section)
assert len(files) == 24, files
flags = ['--target=aarch64-linux-android35','-O2','-flto','-Wall','-Wextra','-Wconversion','-Wsign-conversion',
         '-Wno-unused-parameter','-Wno-sign-compare','-Wno-unused-function','-Icore',
         '-DTARGET_CONFIG_H="kernel/target.h"','-std=c++23','-fno-rtti']
commands=[]
for filename in files:
    obj = out/(filename.replace('/','_')+'.o')
    commands.append([str(compiler),*flags,'-c',filename,'-o',str(obj)])
version=subprocess.check_output([str(compiler),'--version']).decode()
(out/'compiler.txt').write_text(version,encoding='utf-8')
(out/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
def run(command):
    p=subprocess.run(command,cwd=source/'src',capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
    return {'command':command,'returncode':p.returncode,'output':p.stdout+p.stderr}
start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(run,commands))
(out/'compile-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
errors=[r for r in results if r['returncode']]
if errors:
    for r in errors:print(r['output'])
    raise SystemExit(f'{len(errors)} compilation units failed')
binary=out/'ghostlock'
link=[str(compiler),'--target=aarch64-linux-android35',*[r[-1] for r in commands],'-fPIE','-pie','-pthread','-flto','-static-libstdc++','-o',str(binary)]
result=run(link)
(out/'link-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
if result['returncode']:
    print(result['output']);raise SystemExit('Link failed')
manifest={'source':str(source),'label':label,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
          'bytes':binary.stat().st_size,'elapsed_seconds':time.monotonic()-start,'warnings':sum('warning:' in r['output'] for r in results),
          'source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip()}
(out/'build.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest),flush=True)

subprocess.run([str(compiler.parent/'llvm-strip.exe'), '--strip-all', str(binary), '-o', str(out/'ghostlock-arm64')], check=True)
print('Stripped SHA256:', hashlib.sha256((out/'ghostlock-arm64').read_bytes()).hexdigest())
