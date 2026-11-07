"""Check source-only boundaries; do not execute legacy recipes."""
from pathlib import Path
import argparse
import ast
import json
import re

ROOT=Path(__file__).resolve().parents[1]
BINARY_SUFFIXES={'.apk','.aab','.so','.dll','.exe','.zip','.7z','.pyc','.pyo','.jks','.keystore','.pem','.key','.png','.jpg','.jpeg','.mp3','.ogg','.wav','.mp4','.assetbundle'}
FORBIDDEN_DIRS={'.git','__pycache__','inputs','work','dist','.local-baseline','server19-run'}
FORBIDDEN_DATA={'account.json','server19_protocol_schema.json','server19_story_act_rewards.json','server19_virtual_friend_profiles.json'}
def check(root):
    issues=[];python_count=0;files=[]
    for path in sorted(root.rglob('*')):
        name=path.relative_to(root).as_posix()
        if path.is_symlink():issues.append({'path':name,'kind':'symbolic link'});continue
        if path.is_dir():
            if path.name in FORBIDDEN_DIRS:issues.append({'path':name,'kind':'local/generated directory'})
            continue
        files.append(name)
        if path.suffix.lower() in BINARY_SUFFIXES or path.name in FORBIDDEN_DATA:issues.append({'path':name,'kind':'non-source payload'})
        try:text=path.read_text(encoding='utf-8-sig')
        except UnicodeError:issues.append({'path':name,'kind':'non-text payload'});continue
        if path.suffix=='.py':
            python_count+=1
            try:
                tree=ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node,ast.Constant) and isinstance(node.value,str):
                        if re.search(r'(?:^|[\s"\x27])(?:[A-Za-z]:[\\/](?![nrt][\\nrt])|/home/|/Users/|\\\\[A-Za-z0-9_-]+\\)',node.value):
                            issues.append({'path':name,'kind':'absolute host path literal','line':node.lineno})
            except SyntaxError as error:issues.append({'path':name,'kind':'Python syntax','line':error.lineno})
        if re.search(r'(?<![\d.])(?:192\.168\.\d{1,3}\.\d{1,3}|10\.(?:\d{1,3}\.){2}\d{1,3}|100\.(?:\d{1,3}\.){2}\d{1,3})(?![\d.])',text):
            issues.append({'path':name,'kind':'private network endpoint'})
        emails=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text)
        if any(not email.endswith('@example.invalid') for email in emails):issues.append({'path':name,'kind':'email requiring review'})
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',text):issues.append({'path':name,'kind':'private key'})
        if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})',text):issues.append({'path':name,'kind':'credential pattern'})
    return {'status':'PASS' if not issues else 'FAIL','files':len(files),'python_sources':python_count,'issues':issues}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();result=check(args.root);print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)
if __name__=='__main__':main()
