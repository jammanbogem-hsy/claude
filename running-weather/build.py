"""런웨더 빌드: src/app.src.html + SEED CSS → app.html(미리보기 페이지) + index.html(단독 실행 파일)"""
from pathlib import Path
here = Path(__file__).parent
src = (here / "src/app.src.html").read_text()
seed = (here / "vendor/seed-design/seed-subset.css").read_text()
page = src.replace("/*@SEED_CSS@*/", seed)
(here / "app.html").write_text(page)
head_end = page.index("</style>", page.index("/* 레이아웃")) + len("</style>")
doc = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
       '<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}</style>\n'
       + page[:head_end] + '\n</head>\n<body>\n' + page[head_end:] + '\n</body>\n</html>\n')
(here / "index.html").write_text(doc)
print("app.html", len(page), "bytes / index.html", len(doc), "bytes")
