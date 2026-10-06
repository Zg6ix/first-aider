# -*- coding: utf-8 -*-
"""
通用证书登记站构建脚本。
读取 data/certs.csv + files/ 下的证书文件，生成静态网站到 _site/。
用法: python build/build.py  (在仓库根目录运行)
依赖: pymupdf, pillow
"""
import os, re, csv, json, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'certs.csv')
FILES = os.path.join(ROOT, 'files')
OUT = os.path.join(ROOT, '_site')

IMG_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def read_rows():
    # 兼容 Excel 存的 UTF-8(BOM) 和 GBK
    for enc in ('utf-8-sig', 'gbk', 'utf-8'):
        try:
            with open(DATA, encoding=enc, newline='') as f:
                rows = list(csv.DictReader(f))
            return rows
        except UnicodeDecodeError:
            continue
    raise SystemExit('无法读取 data/certs.csv 的编码')


def col(row, *names):
    for n in names:
        for k in row:
            if k and k.strip() == n:
                v = (row[k] or '').strip()
                if v:
                    return v
    return ''


def slugify(s):
    s = re.sub(r'[^A-Za-z0-9一-鿿]+', '-', s).strip('-').lower()
    return s or 'x'


def team_key(t):
    m = re.match(r'(\d+)T$', t)
    if m:
        return (0, int(m.group(1)), t)
    order = {'HSE部': 1, '行政部': 2, '施工技术部': 3}
    if t in order:
        return (1, order[t], t)
    if t == '未分组':
        return (3, 0, t)
    return (2, 0, t)


def make_thumb(src, dst):
    ext = os.path.splitext(src)[1].lower()
    if ext == '.pdf':
        import pymupdf
        pg = pymupdf.open(src)[0]
        pg.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2)).save(dst)
    elif ext in IMG_EXT:
        from PIL import Image
        im = Image.open(src).convert('RGB')
        w = 900
        if im.width > w:
            im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        im.save(dst, 'PNG')
    else:
        raise ValueError('不支持的文件类型: ' + ext)


def build():
    rows = read_rows()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, 'thumbs'))
    os.makedirs(os.path.join(OUT, 'files'))

    cat_order = []            # 类别按首次出现顺序
    cats = {}                 # cat -> {team -> [item]}
    seen_slug = set()
    warnings = []

    for i, row in enumerate(rows):
        fn = col(row, '文件名', 'file', '文件')
        if not fn:
            warnings.append(f'第{i+2}行: 缺少文件名，跳过'); continue
        src = os.path.join(FILES, fn)
        if not os.path.exists(src):
            warnings.append(f'第{i+2}行: files/ 里找不到 "{fn}"，跳过'); continue
        ext = os.path.splitext(fn)[1].lower()
        cat = col(row, '类别', '证书类别', 'category') or '未分类'
        cn = col(row, '中文名', '姓名', 'name_cn')
        en = col(row, '英文名', 'name_en', 'English')
        number = col(row, '证书编号', '编号', 'number', 'eCard Code')
        issue = col(row, '签发日期', '签发', 'issue', '发证日期')
        expiry = col(row, '有效期至', '有效期', 'expiry', 'renew')
        team = col(row, '队伍/部门', '队伍', '部门', 'team', 'group') or '未分组'

        base = slugify(en or cn or number or fn)
        slug = base
        n = 2
        while slug in seen_slug:
            slug = f'{base}-{n}'; n += 1
        seen_slug.add(slug)

        try:
            make_thumb(src, os.path.join(OUT, 'thumbs', slug + '.png'))
        except Exception as e:
            warnings.append(f'第{i+2}行: 缩略图生成失败 ({fn}): {e}'); continue
        shutil.copy(src, os.path.join(OUT, 'files', slug + ext))

        item = {'cn': cn, 'en': en, 'number': number, 'issue': issue,
                'expiry': expiry, 'slug': slug, 'ext': ext}
        if cat not in cats:
            cats[cat] = {}; cat_order.append(cat)
        cats[cat].setdefault(team, []).append(item)

    # 组装有序结构
    CATS = []
    for ci, cat in enumerate(cat_order):
        groups = []
        for ti, team in enumerate(sorted(cats[cat], key=team_key)):
            items = sorted(cats[cat][team], key=lambda x: (x['cn'] or x['en'] or x['number']))
            groups.append({'team': team, 'label': team, 'anchor': f'c{ci}t{ti}', 'items': items})
        total = sum(len(g['items']) for g in groups)
        CATS.append({'cat': cat, 'anchor': f'c{ci}', 'total': total, 'groups': groups})

    html = render(CATS)
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)
    open(os.path.join(OUT, '.nojekyll'), 'w').write('')

    total = sum(c['total'] for c in CATS)
    print(f'✅ 构建完成: {total} 张证书, {len(CATS)} 个类别 -> _site/')
    for w in warnings:
        print('⚠️ ', w)
    return total


def render(CATS):
    data = json.dumps(CATS, ensure_ascii=False)
    total = sum(c['total'] for c in CATS)
    return TEMPLATE.replace('__DATA__', data).replace('__TOTAL__', str(total)).replace('__NCAT__', str(len(CATS)))


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GPP项目第三方证书登记网站</title>
<style>
  :root{--red:#C8102E;--red-d:#9e0c24;--ink:#1a1a1a;--muted:#6b7280;--bg:#f4f5f7;--card:#fff;--line:#e5e7eb;--radius:14px;--nav:196px;--top:112px}
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;overflow-x:hidden}
  header{background:linear-gradient(135deg,var(--red),var(--red-d));color:#fff;padding:20px 16px 16px;text-align:center}
  header h1{margin:0 0 3px;font-size:20px;font-weight:700}
  header p{margin:0;font-size:12.5px;opacity:.9}
  .bar{position:sticky;top:0;z-index:20;background:var(--bg);padding:12px 16px 10px;border-bottom:1px solid var(--line)}
  .barin{max-width:1180px;margin:0 auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .search{flex:1;min-width:180px;padding:11px 14px;font-size:15px;border:1px solid var(--line);border-radius:10px;background:#fff;outline:none}
  .search:focus{border-color:var(--red)}
  .toggle{display:flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
  .toggle button{border:0;background:#fff;padding:10px 14px;font-size:13.5px;font-weight:600;color:var(--muted);cursor:pointer}
  .toggle button.on{background:var(--red);color:#fff}
  .layout{max-width:1180px;margin:0 auto;padding:0 16px 24px;display:flex;gap:18px;align-items:flex-start}
  aside{position:sticky;top:var(--top);width:var(--nav);flex:0 0 var(--nav);align-self:flex-start;max-height:calc(100vh - var(--top) - 16px);overflow:auto;padding-top:14px}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px;text-align:center}
  .stat .big{font-size:26px;font-weight:800;color:var(--red);line-height:1}
  .stat .lbl{font-size:12px;color:var(--muted);margin-top:4px}
  .navlist{display:flex;flex-direction:column;gap:4px}
  .navlist a{display:flex;justify-content:space-between;align-items:center;text-decoration:none;color:var(--ink);font-size:13.5px;padding:8px 11px;border-radius:9px;border:1px solid transparent;gap:6px}
  .navlist a:hover{background:#fff;border-color:var(--line)}
  .navlist a.all{font-weight:700}
  .navlist a .n{font-size:12px;color:#fff;background:var(--red);border-radius:999px;padding:1px 8px;min-width:24px;text-align:center}
  .navlist a.all .n{background:var(--ink)}
  main{flex:1;min-width:0;padding-top:14px}
  .cat{scroll-margin-top:var(--top)}
  .cathead{font-size:19px;font-weight:800;margin:20px 2px 6px;padding-bottom:8px;border-bottom:3px solid var(--red);color:var(--red-d)}
  .cathead .cn{font-size:13px;font-weight:600;color:var(--muted);margin-left:8px}
  .group{scroll-margin-top:var(--top)}
  .ghead{display:flex;align-items:center;gap:10px;margin:14px 2px 12px}
  .ghead .tag{background:var(--red);color:#fff;font-size:14px;font-weight:700;padding:4px 13px;border-radius:999px}
  .ghead .gc{font-size:12.5px;color:var(--muted)}
  .ghead .line{flex:1;height:1px;background:var(--line)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:15px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;transition:box-shadow .15s,transform .15s}
  .card:hover{box-shadow:0 6px 20px rgba(0,0,0,.09);transform:translateY(-2px)}
  .thumb{display:block;background:#fafafa;border-bottom:1px solid var(--line);aspect-ratio:1.6/1;overflow:hidden}
  .thumb img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
  .cbody{padding:12px 14px 14px;display:flex;flex-direction:column;gap:8px;flex:1}
  .name{font-size:17px;font-weight:700;margin:0;line-height:1.2}
  .name .en{display:block;font-size:12px;font-weight:500;color:var(--muted);margin-top:2px}
  .rows{font-size:12.5px;color:var(--muted);line-height:1.55}
  .rows .k{display:inline-block;min-width:60px}
  .rows b{color:var(--ink);font-weight:600}
  .btns{display:flex;gap:8px;margin-top:auto;padding-top:4px}
  .btn{flex:1;text-align:center;text-decoration:none;font-size:13px;font-weight:600;padding:9px 0;border-radius:9px;border:1px solid var(--line);color:var(--ink);background:#fff}
  .btn.primary{background:var(--red);color:#fff;border-color:var(--red)}
  .tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}
  .tbl th,.tbl td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line)}
  .tbl th{background:#faf0f1;color:var(--red-d);font-weight:700;font-size:12.5px}
  .tbl tr:last-child td{border-bottom:0}
  .tbl td.c{color:var(--muted)}
  .tbl td .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
  .tbl a{color:var(--red);text-decoration:none;font-weight:600}
  .empty{text-align:center;color:var(--muted);padding:40px;display:none}
  footer{text-align:center;color:var(--muted);font-size:12px;padding:24px 16px 32px}
  @media(max-width:820px){
    :root{--top:10px}
    .layout{flex-direction:column;gap:0}
    aside{position:static;width:auto;flex:none;max-height:none;overflow:visible;padding-top:10px;background:var(--bg)}
    .stat{display:none}
    .navlist{flex-direction:row;flex-wrap:wrap;overflow:visible;gap:6px;padding-bottom:6px}
    .navlist a{flex:0 0 auto;border:1px solid var(--line);background:#fff;padding:6px 10px;font-size:12.5px}
    .navlist a.all{border-color:var(--ink)}
    main{padding-top:4px}
    .cat,.group{scroll-margin-top:72px}
    .tbl{display:block;overflow-x:auto;white-space:nowrap}
  }
</style>
</head>
<body>
<span id="top"></span>
<header>
  <h1>GPP项目第三方证书登记网站</h1>
  <p>Third-Party Certificate Registry · 扫码查询 / 下载</p>
</header>
<div class="bar"><div class="barin">
  <input class="search" id="q" placeholder="🔍 搜索 姓名 / 编号 / 类别 / 队伍…" autocomplete="off">
  <div class="toggle">
    <button id="vCard" class="on" onclick="setView('card')">卡片</button>
    <button id="vList" onclick="setView('list')">名单</button>
  </div>
</div></div>
<div class="layout">
  <aside>
    <div class="stat"><div class="big" id="sTotal"></div><div class="lbl">证书总数</div></div>
    <div class="stat"><div class="big" id="sCat"></div><div class="lbl">证书类别</div></div>
    <nav class="navlist" id="nav"></nav>
  </aside>
  <main>
    <div id="content"></div>
    <div class="empty" id="empty">没有找到匹配项 · No match</div>
  </main>
</div>
<footer>共 <span id="fTotal"></span> 张证书 · GPP项目第三方证书登记网站</footer>
<script>
const CATS=__DATA__;
const TOTAL=__TOTAL__, NCAT=__NCAT__;
let view='card', kw='';
const content=document.getElementById('content'), empty=document.getElementById('empty'), nav=document.getElementById('nav');
document.getElementById('sTotal').textContent=TOTAL;
document.getElementById('sCat').textContent=NCAT;
document.getElementById('fTotal').textContent=TOTAL;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function hit(it){if(!kw)return true;const k=kw;return (it.cn||'').toLowerCase().includes(k)||(it.en||'').toLowerCase().includes(k)||(it.number||'').toLowerCase().includes(k)}
function catLabel(cat){const m=cat.split(/\s+/);return {main:m[0],sub:m.slice(1).join(' ')}}
// 过滤
function filtered(){
  const out=[];
  for(const c of CATS){
    const catMatch=!kw||c.cat.toLowerCase().includes(kw);
    const groups=[];
    for(const g of c.groups){
      const teamMatch=!kw||g.label.toLowerCase().includes(kw);
      const items=(catMatch||teamMatch)?g.items:g.items.filter(hit);
      if(items.length)groups.push({g,items});
    }
    if(groups.length)out.push({c,groups});
  }
  return out;
}
// 导航：单类别时按队伍，多类别时按类别
function buildNav(){
  let h='<a class="all" href="#top">全部<span class="n">'+TOTAL+'</span></a>';
  if(CATS.length===1){
    for(const g of CATS[0].groups) h+='<a href="#'+g.anchor+'">'+esc(g.label)+'<span class="n">'+g.items.length+'</span></a>';
  }else{
    for(const c of CATS) h+='<a href="#'+c.anchor+'">'+esc(catLabel(c.cat).main)+'<span class="n">'+c.total+'</span></a>';
  }
  nav.innerHTML=h;
}
function cardHtml(it){
  const same=!it.cn||it.cn===it.en||!it.en;
  const nm=same?esc(it.cn||it.en):esc(it.cn)+'<span class="en">'+esc(it.en)+'</span>';
  const p='files/'+encodeURIComponent(it.slug)+it.ext;
  const t='thumbs/'+encodeURIComponent(it.slug)+'.png';
  let rows='';
  if(it.number)rows+='<div><span class="k">证书编号</span><b>'+esc(it.number)+'</b></div>';
  if(it.issue)rows+='<div><span class="k">签发日期</span><b>'+esc(it.issue)+'</b></div>';
  if(it.expiry)rows+='<div><span class="k">有效期至</span><b>'+esc(it.expiry)+'</b></div>';
  return '<div class="card"><a class="thumb" href="'+p+'" target="_blank" rel="noopener"><img loading="lazy" src="'+t+'" alt="'+esc(it.cn||it.en)+'"></a>'+
  '<div class="cbody"><h3 class="name">'+nm+'</h3><div class="rows">'+rows+'</div>'+
  '<div class="btns"><a class="btn" href="'+p+'" target="_blank" rel="noopener">查看</a><a class="btn primary" href="'+p+'" download>下载</a></div></div></div>';
}
function render(){
  const fg=filtered();let h='';
  for(const {c,groups} of fg){
    const cl=catLabel(c.cat);
    h+='<div class="cat" id="'+c.anchor+'"><div class="cathead">'+esc(cl.main)+(cl.sub?'<span class="cn">'+esc(cl.sub)+'</span>':'')+'</div>';
    for(const {g,items} of groups){
      h+='<div class="group" id="'+g.anchor+'"><div class="ghead"><span class="tag">'+esc(g.label)+'</span><span class="gc">'+items.length+' 人</span><span class="line"></span></div>';
      if(view==='card'){
        h+='<div class="grid">'+items.map(cardHtml).join('')+'</div>';
      }else{
        h+='<table class="tbl"><thead><tr><th>中文名</th><th>英文名</th><th>证书编号</th><th>签发</th><th>有效期至</th><th>文件</th></tr></thead><tbody>'+
        items.map(it=>'<tr><td><b>'+esc(it.cn||'—')+'</b></td><td class="c">'+esc(it.en||'—')+'</td><td><span class="mono">'+esc(it.number||'—')+'</span></td><td class="c">'+esc(it.issue||'—')+'</td><td class="c">'+esc(it.expiry||'—')+'</td><td><a href="files/'+encodeURIComponent(it.slug)+it.ext+'" target="_blank" rel="noopener">查看/下载</a></td></tr>').join('')+
        '</tbody></table>';
      }
      h+='</div>';
    }
    h+='</div>';
  }
  content.innerHTML=h;
  empty.style.display=fg.length?'none':'block';
}
function setView(v){view=v;document.getElementById('vCard').classList.toggle('on',v==='card');document.getElementById('vList').classList.toggle('on',v==='list');render();}
document.getElementById('q').addEventListener('input',function(e){kw=e.target.value.trim().toLowerCase();render();});
buildNav();render();
</script>
</body>
</html>'''

if __name__ == '__main__':
    build()
