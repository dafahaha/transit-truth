import io, re, subprocess, sys

with io.open(r'D:\github项目\transit-truth\index.html', 'r', encoding='utf-8') as f:
    html = f.read()

m = re.search(r'<script type="module">([\s\S]*?)</script>', html)
if not m:
    print('module script not found')
    sys.exit(1)

js = m.group(1)
with io.open(r'D:\github项目\transit-truth\_check.mjs', 'w', encoding='utf-8', newline='') as f:
    f.write(js)
print('extracted JS len:', len(js))

# 用 node --check 验证
r = subprocess.run(['node', '--check', r'D:\github项目\transit-truth\_check.mjs'],
                   capture_output=True, text=True)
print('node exit:', r.returncode)
if r.returncode != 0:
    print('STDERR:', r.stderr[:2000])
else:
    print('JS 语法 OK')
